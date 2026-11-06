import os
import tempfile
import unittest
from io import BytesIO

from cryptography.fernet import Fernet
from PIL import Image

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

from recipe_app import create_app, db
from recipe_app.models import Recipe, User


class AtelierAppTests(unittest.TestCase):
    def setUp(self):
        self.uploads = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "UPLOAD_FOLDER": self.uploads.name,
                "SECRET_KEY": "test-secret-key-that-is-long-enough",
                "FERNET_KEY": Fernet.generate_key().decode(),
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.uploads.cleanup()

    def register(self, username, email):
        return self.client.post(
            "/auth/inscription",
            data={
                "username": username,
                "email": email,
                "password": "un-mot-de-passe-solide-123",
                "password_confirmation": "un-mot-de-passe-solide-123",
            },
            follow_redirects=True,
        )

    def create_recipe(self, title="Soupe du marché"):
        return self.client.post(
            "/recettes/nouvelle",
            data={
                "title": title,
                "description": "Une soupe simple et réconfortante pour le soir.",
                "ingredients": "2 carottes\n1 oignon\n1 litre de bouillon",
                "instructions": "Éplucher les légumes.\nLes cuire dans le bouillon.",
                "category": "Plat",
                "prep_minutes": "35",
                "servings": "4",
            },
            follow_redirects=False,
        )

    def test_registration_encrypts_email_and_recipe_is_public_json(self):
        response = self.register("camille", "Camille@exemple.fr")
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            user = User.query.one()
            self.assertEqual(user.email, "camille@exemple.fr")
            self.assertNotIn(b"camille@exemple.fr", user.email_encrypted)
        created = self.create_recipe()
        self.assertEqual(created.status_code, 302)
        result = self.client.get("/recettes/api/recipes?q=Soupe")
        self.assertEqual(result.status_code, 200)
        payload = result.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["data"][0]["author"], "camille")
        missing_recipe = self.client.get("/recettes/api/recipes/9999")
        self.assertEqual(missing_recipe.status_code, 404)
        self.assertEqual(missing_recipe.mimetype, "application/json")

    def test_only_recipe_owner_or_admin_can_edit_or_delete(self):
        self.register("alice", "alice@example.fr")
        self.assertEqual(self.create_recipe().status_code, 302)
        with self.client.session_transaction() as session:
            session.clear()
        self.register("bruno", "bruno@example.fr")
        with self.app.app_context():
            recipe_id = Recipe.query.one().id
        self.assertEqual(self.client.get(f"/recettes/{recipe_id}/modifier").status_code, 403)
        self.assertEqual(
            self.client.post(f"/recettes/{recipe_id}/supprimer").status_code, 403
        )
        self.assertEqual(self.client.get("/auth/admin").status_code, 403)

    def test_registration_rejects_short_password(self):
        response = self.client.post(
            "/auth/inscription",
            data={
                "username": "camille",
                "email": "camille@example.fr",
                "password": "short",
                "password_confirmation": "short",
            },
        )
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(User.query.count(), 0)

    def test_recipe_detail_comments_and_search_pages_render(self):
        self.register("camille", "camille@example.fr")
        self.assertEqual(self.create_recipe("Velouté de carottes").status_code, 302)
        with self.app.app_context():
            recipe_id = Recipe.query.one().id
        comment_response = self.client.post(
            f"/recettes/{recipe_id}/commentaires",
            data={"body": "Le petit plus : une pincée de cumin !"},
            follow_redirects=True,
        )
        self.assertEqual(comment_response.status_code, 200)
        self.assertIn(b"pinc", comment_response.data)
        self.assertEqual(self.client.get("/?q=carottes").status_code, 200)
        for path in ("/conseils", "/a-propos", f"/recettes/{recipe_id}"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_avatar_upload_is_reencoded_and_served_as_webp(self):
        self.register("camille", "camille@example.fr")
        image_bytes = BytesIO()
        Image.new("RGB", (16, 16), color="orange").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        response = self.client.post(
            "/auth/profil",
            data={"avatar": (image_bytes, "photo.png")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            filename = User.query.one().avatar_filename
        self.assertRegex(filename, r"^[a-f0-9]{32}\.webp$")
        avatar_response = self.client.get(f"/auth/avatar/{filename}")
        self.assertEqual(avatar_response.mimetype, "image/webp")
        avatar_response.close()

    def test_avatar_rejects_non_image_upload(self):
        self.register("camille", "camille@example.fr")
        response = self.client.post(
            "/auth/profil",
            data={"avatar": (BytesIO(b"not an image"), "photo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertIsNone(User.query.one().avatar_filename)

    def test_csrf_is_required_when_enabled(self):
        protected_app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "UPLOAD_FOLDER": self.uploads.name,
                "SECRET_KEY": "test-secret-key-that-is-long-enough",
                "FERNET_KEY": Fernet.generate_key().decode(),
            }
        )
        response = protected_app.test_client().post("/auth/inscription", data={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
