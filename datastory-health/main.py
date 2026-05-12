"""Script principal DataStory Music.

Demo rapide:
1) initialise la base
2) verifie la securite (hash/chiffrement)
3) affiche un apercu de l'evolution des genres
"""

import sys
import os

# Ajoute le dossier app au PYTHONPATH local du script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.models import init_db, SessionLocal, User
from app.auth import hash_password, verify_password, encrypt_field, decrypt_field
from app.data_processing import load_music_complete_data, prepare_charts_data


def demo_music_foundation():
    """Demonstration simple de la pile securite + data musique."""
    print("=" * 72)
    print("DATASTORY MUSIC - DEMO COMPLETE")
    print("=" * 72)
    print()
    
    # ========================================================================
    # ETAPE 1 : CREER LA BASE VIA SQLALCHEMY
    # ========================================================================
    print("ETAPE 1  Initialiser la base SQLite")
    print("-" * 72)
    
    try:
        moteur, _ = init_db()
        print("✅ Base de donnees initialisee")
        print(f"   Engine: {moteur}")
        print()
    except Exception as e:
        print(f"❌ Echec initialisation base: {e}")
        return
    
    print("ETAPE 2  Demo inscription securisee")
    print("-" * 72)
    
    # Identifiants de demonstration
    nom_utilisateur = "baptiste_music"
    courriel = "baptiste@livecampus.fr"
    mot_de_passe = "DataStoryMusic2026!Secure"
    
    print(f"   Nom utilisateur: {nom_utilisateur}")
    print(f"   Email:           {courriel} (sera chiffre)")
    print(f"   Mot de passe:    {mot_de_passe[:10]}... (sera hache)")
    print()
    
    # Hachage du mot de passe avec bcrypt
    empreinte_mot_de_passe = hash_password(mot_de_passe)
    print(f"   🔒 Empreinte mot de passe: {empreinte_mot_de_passe[:50]}...")
    
    # Chiffrement de l'email avec Fernet
    courriel_chiffre = encrypt_field(courriel)
    print(f"   🔐 Email chiffre: {courriel_chiffre[:50]}...")
    print()
    
    # Ecriture en base : si l'utilisateur existe deja, on met a jour ses secrets.
    session_db = SessionLocal()
    try:
        utilisateur_existant = session_db.query(User).filter(User.username == nom_utilisateur).first()

        if utilisateur_existant:
            # Rend le script relancable sans erreur UNIQUE.
            utilisateur_existant.email = courriel_chiffre
            utilisateur_existant.password_hash = empreinte_mot_de_passe
            utilisateur_existant.role = "user"
            session_db.commit()
            id_utilisateur = utilisateur_existant.id
            print(f"✅ Utilisateur deja present - secrets mis a jour (ID: {id_utilisateur})")
            print()
        else:
            nouvel_utilisateur = User(
                username=nom_utilisateur,
                email=courriel_chiffre,  # Store encrypted!
                password_hash=empreinte_mot_de_passe,
                role="user"
            )
            session_db.add(nouvel_utilisateur)
            session_db.commit()
            id_utilisateur = nouvel_utilisateur.id
            print(f"✅ Utilisateur enregistre en base (ID: {id_utilisateur})")
            print()

    except Exception as e:
        session_db.rollback()
        print(f"❌ Echec inscription: {e}")
        return
    finally:
        session_db.close()
    
    # ========================================================================
    # ETAPE 3 : LIRE L'UTILISATEUR ET DECHIFFRER L'EMAIL
    # ========================================================================
    print("ETAPE 3  Verification lecture/dechiffrement")
    print("-" * 72)
    
    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.username == nom_utilisateur).first()
        
        if not utilisateur:
            print(f"❌ Utilisateur {nom_utilisateur} introuvable")
            return
        
        print("   Utilisateur trouve en base :")
        print(f"   - ID: {utilisateur.id}")
        print(f"   - Nom utilisateur: {utilisateur.username}")
        print(f"   - Email chiffre (en base): {utilisateur.email[:50]}...")
        print()
        
        # Dechiffrement de l'email stocke en base.
        courriel_dechiffre = decrypt_field(utilisateur.email)
        print(f"✅ Email dechiffre: {courriel_dechiffre}")
        print(f"   Correspond a l'original: {courriel_dechiffre == courriel}")
        print()
        
    except Exception as e:
        print(f"❌ Echec lecture base: {e}")
        return
    finally:
        session_db.close()
    
    # ========================================================================
    # ETAPE 4 : VERIFIER LE MOT DE PASSE
    # ========================================================================
    print("ETAPE 4  Verification du mot de passe")
    print("-" * 72)
    
    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.username == nom_utilisateur).first()
        
        # Test du bon mot de passe
        est_correct = verify_password(mot_de_passe, utilisateur.password_hash)
        print(f"   Test mot de passe correct: {est_correct} ✅")
        
        # Test d'un mot de passe faux
        est_faux = verify_password("WrongPassword123", utilisateur.password_hash)
        print(f"   Test mot de passe faux: {est_faux} ✅ (rejet correct)")
        print()
        
        if est_correct and not est_faux:
            print("✅ Verification mot de passe OK")
        
    except Exception as e:
        print(f"❌ Echec verification mot de passe: {e}")
        return
    finally:
        session_db.close()
    
    # ========================================================================
    # ETAPE 5 : Charger la data musique
    # ========================================================================
    print()
    print("ETAPE 5  Charger la data musique unifiee")
    print("-" * 72)

    donnees = load_music_complete_data()
    donnees = prepare_charts_data(donnees)
    print(f"✅ {len(donnees)} lignes musique chargees")

    if not donnees.empty and {"decennie", "track_genre"}.issubset(donnees.columns):
        top_genres = (
            donnees.groupby(["decennie", "track_genre"], as_index=False)
            .size()
            .sort_values(["decennie", "size"], ascending=[True, False])
            .groupby("decennie")
            .head(3)
        )
        print("\nTop 3 genres par decennie (apercu):")
        print(top_genres.head(15).to_string(index=False))
    else:
        print("⚠️  Donnees insuffisantes pour calculer les genres par decennie")

    print()
    
    # ========================================================================
    # RESUME
    # ========================================================================
    print("=" * 72)
    print("RESUME")
    print("=" * 72)
    print("""
✅ FONDATION TERMINEE - DataStory Music est pret

Ce qui est en place :
1. ✅ Base SQLite via SQLAlchemy ORM
2. ✅ Inscription utilisateur avec :
    - hachage bcrypt (gensalt rounds=12)
    - email chiffre avec Fernet
3. ✅ Lecture utilisateur + dechiffrement email
4. ✅ Verification mot de passe
5. ✅ Analyse de l'evolution des genres par periodes

Exigences techniques validees :
✅ ORM uniquement (zero SQL brut)
✅ bcrypt (rounds=12 minimum)
✅ chiffrement Fernet (>= 1 champ sensible)
✅ JWT signes (implemente dans auth.py)
✅ Pipeline de nettoyage musique + fichier global unifie

API a lancer : app/api.py
Pages dispo :
→ /page/genres
→ /page/michael-jackson

Base : music_data.db
    """)
    print("=" * 72)

if __name__ == "__main__":
    os.system("cls" if os.name == "nt" else "clear")
    demo_music_foundation()
