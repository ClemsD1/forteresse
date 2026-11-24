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

    def test_search_payload_is_treated_as_data_not_sql(self):
        self.register("camille", "camille@example.fr")
        self.assertEqual(self.create_recipe("Soupe normale").status_code, 302)

        response = self.client.get("/?q=' OR '1'='1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Soupe normale", response.data)

        api_response = self.client.get("/recettes/api/recipes?q=' OR '1'='1")
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.get_json()["count"], 0)

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

    def test_user_supplied_html_is_rendered_as_text(self):
        self.register("camille", "camille@example.fr")
        payload = "<img src=x onerror=alert(1)>"
        self.assertEqual(self.create_recipe(payload).status_code, 302)
        with self.app.app_context():
            recipe_id = Recipe.query.one().id

        comment_response = self.client.post(
            f"/recettes/{recipe_id}/commentaires",
            data={"body": payload},
        )
        response = self.client.get(f"/recettes/{recipe_id}")

        self.assertEqual(comment_response.status_code, 302)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;img src=x onerror=alert(1)&gt;", response.data)
        self.assertIn(b"<p>&lt;img src=x onerror=alert(1)&gt;</p>", response.data)
        self.assertNotIn(payload.encode(), response.data)

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
        self.assertTrue(os.path.isfile(os.path.join(self.uploads.name, filename)))
        self.assertNotEqual(
            os.path.commonpath([self.app.static_folder, self.uploads.name]),
            self.app.static_folder,
        )
        self.assertRegex(filename, r"^[a-f0-9]{32}\.webp$")
        avatar_response = self.client.get(f"/auth/avatar/{filename}")
        self.assertEqual(avatar_response.mimetype, "image/webp")
        self.assertNotIn("attachment", avatar_response.headers.get("Content-Disposition", ""))
        self.assertEqual(avatar_response.headers["X-Content-Type-Options"], "nosniff")
        avatar_response.close()
        download_response = self.client.get(f"/auth/avatar/{filename}/download")
        self.assertEqual(download_response.mimetype, "image/webp")
        self.assertIn("attachment", download_response.headers["Content-Disposition"])
        self.assertEqual(download_response.headers["X-Content-Type-Options"], "nosniff")
        download_response.close()

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

    def test_avatar_rejects_php_and_svg_even_with_an_allowed_extension(self):
        self.register("camille", "camille@example.fr")
        for filename, contents in (
            ("script.php", b"<?php echo 'not an image'; ?>"),
            ("script.jpg", b"<?php echo 'not an image'; ?>"),
            ("vector.svg", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
        ):
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/auth/profil",
                    data={"avatar": (BytesIO(contents), filename)},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertIsNone(User.query.one().avatar_filename)
        self.assertEqual(os.listdir(self.uploads.name), [])

    def test_avatar_upload_rejects_oversized_request(self):
        self.register("camille", "camille@example.fr")
        boundary = b"upload-test-boundary"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="avatar"; filename="large.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
            + b"x" * (4 * 1024 * 1024 + 1)
            + b"\r\n--" + boundary + b"--\r\n"
        )
        response = self.client.post(
            "/auth/profil",
            data=body,
            content_type=f"multipart/form-data; boundary={boundary.decode()}",
        )
        self.assertEqual(response.status_code, 413)
        response.close()

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

    def test_internal_errors_are_generic_for_users_and_logged_server_side(self):
        self.assertFalse(self.app.debug)
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        def fail():
            raise RuntimeError("secret diagnostic detail")

        self.app.add_url_rule("/test-error", "test_error", fail)
        self.app.add_url_rule(
            "/recettes/api/test-error", "api_test_error", fail
        )
        with self.assertLogs(self.app.logger, level="ERROR") as captured:
            html_response = self.client.get("/test-error")
            api_response = self.client.get("/recettes/api/test-error")

        self.assertEqual(html_response.status_code, 500)
        self.assertIn(b"Erreur interne", html_response.data)
        self.assertIn(b"Un probl\xc3\xa8me inattendu est survenu.", html_response.data)
        self.assertNotIn(b"secret diagnostic detail", html_response.data)
        self.assertNotIn(b"Traceback", html_response.data)
        self.assertEqual(api_response.status_code, 500)
        self.assertEqual(
            api_response.get_json(),
            {
                "error": "internal_server_error",
                "message": "Un problème inattendu est survenu. Veuillez réessayer plus tard.",
            },
        )
        self.assertIn("secret diagnostic detail", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
