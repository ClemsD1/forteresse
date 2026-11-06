from datetime import datetime, timezone

from flask_login import UserMixin

from recipe_app import db
from recipe_app.security import decrypt_email

RECIPE_CATEGORIES = [
    "Entrée", "Plat", "Dessert", "Petit-déjeuner", "Végétarien", "Boisson"
]


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_encrypted = db.Column(db.LargeBinary, nullable=False)
    email_lookup = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="user")
    avatar_filename = db.Column(db.String(80))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    recipes = db.relationship("Recipe", back_populates="author", cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="author", cascade="all, delete-orphan")

    @property
    def email(self):
        return decrypt_email(self.email_encrypted)


class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=False)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, index=True)
    prep_minutes = db.Column(db.Integer, nullable=False)
    servings = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    author = db.relationship("User", back_populates="recipes")
    comments = db.relationship(
        "Comment", back_populates="recipe", cascade="all, delete-orphan", order_by="Comment.created_at"
    )


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False, index=True)
    author = db.relationship("User", back_populates="comments")
    recipe = db.relationship("Recipe", back_populates="comments")
