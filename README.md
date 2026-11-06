# L'Atelier — recettes maison & cuisine à partager

Application web de partage de recettes construite avec Flask, PostgreSQL, SQLAlchemy et Docker Compose. L'interface est en français et s'adapte aux mobiles.

## Démarrer avec Docker

Prérequis : Docker Desktop avec le plugin Compose.

1. Copier `.env.example` vers `.env`.
2. Générer les secrets (Python installé suffit ; aucune dépendance du projet n'est requise) :

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
   ```

3. Renseigner les résultats comme valeurs de `SECRET_KEY` et `FERNET_KEY` dans `.env`, puis définir un long `POSTGRES_PASSWORD`.

   La clé Fernet est une valeur Base64 URL-safe aléatoire de 32 octets. Sa génération avec la bibliothèque standard évite d'avoir à installer `cryptography` dans le Python global de votre ordinateur.
4. Construire et démarrer les services :

   ```powershell
   docker compose up --build
   ```

5. Ouvrir [http://localhost:5000](http://localhost:5000).
6. Dans un second terminal, créer le compte administrateur initial :

   ```powershell
   docker compose exec web flask --app wsgi create-admin
   ```

Les services utilisent un volume nommé pour la base PostgreSQL et un autre pour les avatars. Le serveur HTTP du conteneur est Waitress ; `init-db` crée les tables au démarrage. Pour un vrai produit, remplacez cette initialisation par des migrations versionnées. Derrière un reverse proxy HTTPS, configurez `COOKIE_SECURE=true` dans `.env`.

## Développement local

Python 3.12+ et PostgreSQL sont recommandés. Sans `DATABASE_URL`, l'application utilise une base SQLite locale (utile pour les essais).

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = (py -c "import secrets; print(secrets.token_hex(32))")
$env:FERNET_KEY = (py -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
flask --app wsgi init-db
flask --app wsgi run --debug
```

Dans un autre terminal activé, créer un administrateur avec `flask --app wsgi create-admin`.

## Fonctionnalités

- Inscription, connexion, déconnexion par formulaire POST et profil membre.
- Rôles `user` et `admin`, administration protégée et modération des recettes.
- CRUD des recettes de l'auteur (titre, histoire, catégorie, ingrédients, étapes, durée et portions).
- Commentaires partagés, recherche plein texte simple et filtre par catégorie en base de données.
- Avatar JPEG/PNG/WebP : taille HTTP limitée, vérification du contenu, conversion en WebP et nom de fichier aléatoire.
- API JSON publique : `GET /recettes/api/recipes`, `GET /recettes/api/recipes/<id>`.
- Protection CSRF, requêtes ORM paramétrées, mots de passe hachés, cookies de session HttpOnly/SameSite, en-têtes de sécurité et contrôle des accès par propriétaire.
- Les e-mails sont chiffrés avec Fernet dans la colonne `email_encrypted`. Une empreinte HMAC distincte (`email_lookup`) permet l'unicité et la connexion sans stocker l'adresse en clair. Les deux clés proviennent de variables d'environnement ; sauvegardez `FERNET_KEY` séparément et durablement, car sa perte empêche de déchiffrer les e-mails.

## Parcours d'essai

1. Créer deux comptes membres et un compte admin.
2. Publier une recette avec le premier compte, puis la retrouver sans connexion via la recherche ou l'API.
3. Modifier la recette avec son auteur ; vérifier qu'un autre membre ne peut ni la modifier ni la supprimer.
4. Ajouter un commentaire et un avatar, puis consulter `/auth/admin` avec l'administrateur.

Les routes de modification/suppression et les commentaires utilisent des formulaires POST avec jeton CSRF. Les routes de lecture JSON ne nécessitent pas d'authentification.

## Tests

```powershell
python -m unittest discover -s tests
```
