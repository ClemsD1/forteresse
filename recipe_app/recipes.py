from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from recipe_app import db
from recipe_app.models import Comment, Recipe, RECIPE_CATEGORIES

recipes_bp = Blueprint("recipes", __name__)


def _recipe_from_form(recipe=None):
    values = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "ingredients": request.form.get("ingredients", "").strip(),
        "instructions": request.form.get("instructions", "").strip(),
        "category": request.form.get("category", ""),
    }
    errors = []
    if not 3 <= len(values["title"]) <= 100:
        errors.append("Le titre doit contenir entre 3 et 100 caractères.")
    if not 10 <= len(values["description"]) <= 300:
        errors.append("La description doit contenir entre 10 et 300 caractères.")
    if not 5 <= len(values["ingredients"]) <= 5000:
        errors.append("Les ingrédients doivent contenir entre 5 et 5 000 caractères.")
    if not 10 <= len(values["instructions"]) <= 10000:
        errors.append("Les étapes doivent contenir entre 10 et 10 000 caractères.")
    if values["category"] not in RECIPE_CATEGORIES:
        errors.append("Choisissez une catégorie valide.")
    try:
        prep_minutes = int(request.form.get("prep_minutes", ""))
        servings = int(request.form.get("servings", ""))
        if not 1 <= prep_minutes <= 1440:
            raise ValueError
        if not 1 <= servings <= 100:
            raise ValueError
    except ValueError:
        errors.append("Le temps doit être entre 1 et 1 440 minutes et les portions entre 1 et 100.")
        prep_minutes = servings = 1
    if errors:
        return None, errors
    data = {**values, "prep_minutes": prep_minutes, "servings": servings}
    if recipe:
        for key, value in data.items():
            setattr(recipe, key, value)
        return recipe, []
    return Recipe(**data, user_id=current_user.id), []


def _serialize_recipe(recipe):
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "ingredients": recipe.ingredients.splitlines(),
        "instructions": recipe.instructions.splitlines(),
        "category": recipe.category,
        "prep_minutes": recipe.prep_minutes,
        "servings": recipe.servings,
        "author": recipe.author.username,
        "created_at": recipe.created_at.isoformat(),
        "url": url_for("recipes.detail", recipe_id=recipe.id, _external=False),
    }


@recipes_bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        recipe, errors = _recipe_from_form()
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("recipes/form.html", recipe=None), 400
        db.session.add(recipe)
        db.session.commit()
        flash("Votre recette est maintenant partagée avec la communauté.", "success")
        return redirect(url_for("recipes.detail", recipe_id=recipe.id))
    return render_template("recipes/form.html", recipe=None)


@recipes_bp.get("/<int:recipe_id>")
def detail(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        abort(404)
    return render_template("recipes/detail.html", recipe=recipe)


@recipes_bp.route("/<int:recipe_id>/modifier", methods=["GET", "POST"])
@login_required
def edit(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        abort(404)
    if recipe.user_id != current_user.id and current_user.role != "admin":
        abort(403)
    if request.method == "POST":
        _, errors = _recipe_from_form(recipe)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("recipes/form.html", recipe=recipe), 400
        db.session.commit()
        flash("Votre recette a été mise à jour.", "success")
        return redirect(url_for("recipes.detail", recipe_id=recipe.id))
    return render_template("recipes/form.html", recipe=recipe)


@recipes_bp.post("/<int:recipe_id>/supprimer")
@login_required
def delete(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        abort(404)
    if recipe.user_id != current_user.id and current_user.role != "admin":
        abort(403)
    db.session.delete(recipe)
    db.session.commit()
    flash("La recette a été supprimée.", "success")
    return redirect(url_for("main.index"))


@recipes_bp.post("/<int:recipe_id>/commentaires")
@login_required
def comment(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        abort(404)
    body = request.form.get("body", "").strip()
    if not body or len(body) > 1000:
        flash("Un commentaire doit contenir entre 1 et 1 000 caractères.", "error")
        return redirect(url_for("recipes.detail", recipe_id=recipe_id)), 400
    db.session.add(Comment(body=body, user_id=current_user.id, recipe_id=recipe.id))
    db.session.commit()
    flash("Votre mot doux a été publié.", "success")
    return redirect(url_for("recipes.detail", recipe_id=recipe_id) + "#discussion")


@recipes_bp.get("/api/recipes")
def api_recipes():
    query = Recipe.query
    term = request.args.get("q", "").strip()[:80]
    category = request.args.get("category", "")
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(Recipe.title.ilike(pattern), Recipe.description.ilike(pattern)))
    if category in RECIPE_CATEGORIES:
        query = query.filter_by(category=category)
    elif category:
        return jsonify(error="invalid_category", message="Catégorie inconnue."), 400
    recipes = query.order_by(Recipe.created_at.desc()).limit(50).all()
    return jsonify(data=[_serialize_recipe(recipe) for recipe in recipes], count=len(recipes))


@recipes_bp.get("/api/recipes/<int:recipe_id>")
def api_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None:
        return jsonify(error="not_found", message="Recette introuvable."), 404
    return jsonify(data=_serialize_recipe(recipe))
