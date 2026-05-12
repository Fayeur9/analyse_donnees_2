"""Modeles SQLAlchemy du projet DataStory Music."""

import os
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///music_data.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    """Modele utilisateur pour l'authentification."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username}>"


class MusicChartEntry(Base):
    """Entree de classement issue des charts Billboard."""

    __tablename__ = "music_chart_entries"

    id = Column(Integer, primary_key=True)
    source_chart = Column(String(60), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    song = Column(String(255), nullable=False, index=True)
    artist = Column(String(255), nullable=False, index=True)
    rank = Column(Integer, nullable=False, index=True)
    last_week = Column(Integer)
    peak_position = Column(Integer)
    weeks_in_charts = Column(Integer)
    image_url = Column(Text)

    def __repr__(self):
        return f"<MusicChartEntry {self.source_chart} {self.date} #{self.rank} {self.artist} - {self.song}>"

    @classmethod
    def get_by_period(cls, session, date_debut, date_fin):
        return session.query(cls).filter(cls.date >= date_debut, cls.date <= date_fin).all()

    @classmethod
    def get_by_artist(cls, session, artiste):
        return session.query(cls).filter(cls.artist.ilike(f"%{artiste}%")).all()

    @classmethod
    def get_by_chart(cls, session, chart_name):
        return session.query(cls).filter(cls.source_chart == chart_name).all()


class MusicTrackFeature(Base):
    """Caracteristiques audio des morceaux (dataset train.csv)."""

    __tablename__ = "music_track_features"

    id = Column(Integer, primary_key=True)
    track_id = Column(String(64), nullable=False, unique=True, index=True)
    artists = Column(String(255), nullable=False, index=True)
    album_name = Column(String(255))
    track_name = Column(String(255), nullable=False, index=True)
    popularity = Column(Integer)
    duration_ms = Column(Integer)
    explicit = Column(Boolean)
    danceability = Column(Float)
    energy = Column(Float)
    key = Column(Integer)
    loudness = Column(Float)
    mode = Column(Integer)
    speechiness = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    liveness = Column(Float)
    valence = Column(Float)
    tempo = Column(Float)
    time_signature = Column(Integer)
    track_genre = Column(String(80), index=True)

    def __repr__(self):
        return f"<MusicTrackFeature {self.artists} - {self.track_name} ({self.track_genre})>"

    @classmethod
    def get_by_genre(cls, session, genre):
        return session.query(cls).filter(cls.track_genre == genre).all()

    @classmethod
    def get_by_artist(cls, session, artiste):
        return session.query(cls).filter(cls.artists.ilike(f"%{artiste}%")).all()


def init_db():
    """Cree les tables si elles n'existent pas deja."""
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


if __name__ == "__main__":
    init_db()
    print("Tables creees avec succes")
