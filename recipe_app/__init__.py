import os
from pathlib import Path

import click
from flask import Flask, jsonify, render_template, request
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Connectez-vous pour continuer."
login_manager.login_message_category = "info"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        FERNET_KEY=os.environ.get("FERNET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///" + str(Path(app.instance_path) / "atelier.sqlite")
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", str(Path(app.root_path).parent / "uploads")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY") or not app.config.get("FERNET_KEY"):
        raise RuntimeError("SECRET_KEY et FERNET_KEY doivent être configurées.")
    try:
        Fernet(app.config["FERNET_KEY"].encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise RuntimeError("FERNET_KEY doit être une clé Fernet valide.") from error

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    from recipe_app import models
    from recipe_app.auth import auth_bp
    from recipe_app.main import main_bp
    from recipe_app.recipes import recipes_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(recipes_bp, url_prefix="/recettes")

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.path.startswith("/recettes/api/"):
            return jsonify(error="csrf_invalid", message="Jeton CSRF invalide ou expiré."), 400
        return render_template("error.html", title="Formulaire expiré", message=error.description), 400

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", "La requête ne peut pas être traitée.")
        if request.path.startswith("/recettes/api/"):
            return jsonify(error="bad_request", message=message), 400
        return render_template("error.html", title="Requête invalide", message=message), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(413)
    def file_too_large(_error):
        message = "Le fichier est trop volumineux. La limite est de 4 Mo."
        if request.path.startswith("/recettes/api/"):
            return jsonify(error="file_too_large", message=message), 413
        return render_template("error.html", title="Fichier trop volumineux", message=message), 413

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/recettes/api/"):
            return jsonify(error="not_found", message="Ressource introuvable."), 404
        return render_template(
            "error.html", title="Page introuvable", message="Cette page n'existe pas (ou plus)."
        ), 404

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        db.create_all()
        click.echo("Base de données initialisée.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--username", prompt=True)
    @click.password_option()
    def create_admin(email, username, password):
        """Create the first administrator account."""
        from email_validator import EmailNotValidError, validate_email

        from recipe_app.auth import USERNAME_RE
        from recipe_app.security import email_fingerprint, encrypt_email, normalize_email

        try:
            normalized_email = validate_email(
                normalize_email(email), check_deliverability=False
            ).normalized.lower()
        except EmailNotValidError as error:
            raise click.ClickException("Saisissez une adresse e-mail valide.") from error
        if not USERNAME_RE.fullmatch(username.strip()):
            raise click.ClickException("Le pseudo doit respecter le format autorisé.")
        if not 12 <= len(password) <= 128:
            raise click.ClickException("Le mot de passe doit contenir entre 12 et 128 caractères.")
        admin = models.User(
            email_encrypted=encrypt_email(normalized_email),
            email_lookup=email_fingerprint(normalized_email),
            username=username.strip(),
            password_hash=generate_password_hash(password),
            role="admin",
        )
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise click.ClickException("Cet e-mail ou ce nom d'utilisateur est déjà utilisé.") from error
        click.echo(f"Compte administrateur créé pour {admin.username}.")

    @app.context_processor
    def inject_template_values():
        return {"recipe_categories": models.RECIPE_CATEGORIES}

    return app
