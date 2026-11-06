import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from recipe_app import db
from recipe_app.models import User
from recipe_app.security import email_fingerprint, encrypt_email, is_safe_redirect_target, normalize_email

auth_bp = Blueprint("auth", __name__)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,40}$")


@auth_bp.route("/inscription", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        errors = []
        if not USERNAME_RE.fullmatch(username):
            errors.append("Le pseudo doit contenir 3 à 40 lettres, chiffres, tirets ou underscores.")
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            errors.append("Saisissez une adresse e-mail valide.")
        if not 12 <= len(password) <= 128:
            errors.append("Le mot de passe doit contenir entre 12 et 128 caractères.")
        if password != confirmation:
            errors.append("Les mots de passe ne correspondent pas.")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("auth/register.html"), 400

        user = User(
            username=username,
            email_encrypted=encrypt_email(email),
            email_lookup=email_fingerprint(email),
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Cette adresse e-mail ou ce pseudo est déjà utilisé.", "error")
            return render_template("auth/register.html"), 409
        login_user(user)
        flash("Bienvenue à L'Atelier ! Votre compte est prêt.", "success")
        return redirect(url_for("main.index"))
    return render_template("auth/register.html")


@auth_bp.route("/connexion", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    next_url = request.args.get("next") or request.form.get("next")
    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        user = User.query.filter_by(email_lookup=email_fingerprint(email)).first()
        if len(password) > 128 or user is None or not check_password_hash(user.password_hash, password):
            flash("Adresse e-mail ou mot de passe incorrect.", "error")
            return render_template("auth/login.html", next_url=next_url), 401
        login_user(user, remember=request.form.get("remember") == "on", fresh=True)
        destination = next_url if is_safe_redirect_target(next_url) else url_for("main.index")
        return redirect(destination)
    return render_template("auth/login.html", next_url=next_url)


@auth_bp.post("/deconnexion")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté·e.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        image = request.files.get("avatar")
        if image and image.filename:
            from recipe_app.uploads import save_avatar

            try:
                new_filename = save_avatar(image)
            except ValueError as error:
                flash(str(error), "error")
                return render_template("auth/profile.html"), 400
            old_filename = current_user.avatar_filename
            current_user.avatar_filename = new_filename
            db.session.commit()
            if old_filename:
                from pathlib import Path
                from flask import current_app

                old_path = Path(current_app.config["UPLOAD_FOLDER"]) / old_filename
                if old_path.is_file():
                    old_path.unlink()
            flash("Votre avatar a été mis à jour.", "success")
        else:
            flash("Choisissez une image à envoyer.", "error")
            return render_template("auth/profile.html"), 400
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html")


@auth_bp.get("/avatar/<filename>")
def avatar(filename):
    from flask import abort, current_app, send_from_directory

    if not re.fullmatch(r"[a-f0-9]{32}\.webp", filename):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, mimetype="image/webp")


@auth_bp.get("/admin")
@login_required
def admin():
    if current_user.role != "admin":
        from flask import abort

        abort(403)
    from recipe_app.models import Recipe

    users = User.query.order_by(User.created_at.desc()).limit(100).all()
    recipes = Recipe.query.order_by(Recipe.created_at.desc()).limit(100).all()
    return render_template("auth/admin.html", users=users, recipes=recipes)


@auth_bp.post("/admin/recettes/<int:recipe_id>/supprimer")
@login_required
def admin_delete_recipe(recipe_id):
    if current_user.role != "admin":
        from flask import abort

        abort(403)
    from recipe_app.models import Recipe

    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        from flask import abort

        abort(404)
    db.session.delete(recipe)
    db.session.commit()
    flash("La recette a été supprimée.", "success")
    return redirect(url_for("auth.admin"))
