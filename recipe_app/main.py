from flask import Blueprint, abort, render_template, request
from sqlalchemy import or_

from recipe_app.models import Recipe, RECIPE_CATEGORIES

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    term = request.args.get("q", "").strip()[:80]
    category = request.args.get("category", "")
    query = Recipe.query
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(Recipe.title.ilike(pattern), Recipe.description.ilike(pattern)))
    if category in RECIPE_CATEGORIES:
        query = query.filter_by(category=category)
    elif category:
        abort(400, description="Catégorie inconnue.")
    recipes = query.order_by(Recipe.created_at.desc()).limit(24).all()
    return render_template(
        "main/index.html", recipes=recipes, search_term=term, selected_category=category
    )


@main_bp.get("/conseils")
def tips():
    return render_template("main/tips.html")


@main_bp.get("/a-propos")
def about():
    return render_template("main/about.html")
