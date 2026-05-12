# DataStory Health - Semaine 2, Jour 1 Matin

Analyse narrative des données d'urgences (ER passages 2017-2023 DREES)

## Structure

```
datastory-health/
├── app/
│   ├── models.py              # SQLAlchemy: User + Emergency
│   ├── auth.py                # bcrypt, Fernet, JWT security
│   ├── data_processing.py     # Load & prepare ER data
│   └── api.py                 # Flask API (this afternoon)
├── data/
│   └── dataset.csv            # ER passages data (DREES)
├── tests/
├── main.py                    # TP matin script (demonstrable at 12h30)
├── .env                       # Secrets (JWT + Fernet keys)
├── .gitignore
├── requirements.txt
└── README.md
```

## Objectif 12h30

À 12h30, un script fonctionnel qui :

1. ✅ Crée la base SQLite via SQLAlchemy
2. ✅ Inscrit un utilisateur (password bcrypt, email Fernet)
3. ✅ Lit l'utilisateur et déchiffre l'email
4. ✅ Vérifie le mot de passe via verify_password()

**EXÉCUTER:** `python main.py`

## Sécurité - Week 2

| Requirement | Status | Implementation |
|---|---|---|
| ORM only | ✅ | SQLAlchemy - zero raw SQL |
| bcrypt | ✅ | gensalt(rounds=12) |
| Fernet | ✅ | Email encrypted at rest |
| JWT | ✅ | Signed, verified, HS256 explicit |
| Validation | 🔄 | Pydantic (this afternoon) |
| Rate limiting | 🔄 | Flask limiter (this afternoon) |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Create & populate database, verify security stack
python main.py
```

## Dataset

**DREES ER Passages 2017-2023**
- Source: data.drees.solidarites-sante.gouv.fr
- Columns: region, date, nb_passages, nb_hospitalisation, nb_rapatriement
- Criteria: ✅ >1500 rows, ✅ 8+ columns, ✅ CSV format

## This Afternoon

Flask API with:
- `/register` - User registration
- `/login` - Authentication with JWT
- `/protected` - Protected endpoint example
- `/docs` - OpenAPI auto-documentation
- Rate limiting on `/login`

---

Baptiste Freminet - LiveCampus Master 1
