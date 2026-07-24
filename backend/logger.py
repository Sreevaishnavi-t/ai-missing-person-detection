import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import DB_SQLITE_PATH

# ==============================================================================
# CONCEPT EXPLANATION: What is an ORM and why do we use SQLAlchemy?
# ==============================================================================
# An Object-Relational Mapper (ORM) is a programming technique that translates
# data between relational databases (like SQLite, PostgreSQL, MySQL) and object-
# oriented code (like Python). It maps database tables to Python classes, rows
# to class instances, and table columns to object attributes.
#
# Why we use SQLAlchemy instead of writing raw SQL:
# 1. Abstraction / Portability: SQLAlchemy translates Python operations into
#    the correct SQL dialect dynamically. If we decide to migrate from SQLite
#    to a production database like PostgreSQL or SQL Server later, we only
#    change the connection string; no SQL queries need to be rewritten.
# 2. Safety / SQL Injection Prevention: Writing raw SQL statements using string
#    interpolation (e.g., f"INSERT INTO logs VALUES ('{name}')") exposes the
#    app to SQL injection attacks. SQLAlchemy automatically parameterizes and
#    escapes all inputs.
# 3. Maintainability: The database schema is defined as a Python class. This
#    allows us to use IDE autocomplete, type validation, and static checkers,
#    making it much harder to make spelling or typing mistakes.
# 4. Clean Syntax: Performing operations like inserts and queries uses clean,
#    idiomatic Python methods (e.g., session.add(), session.query()) rather than
#    multiline SQL strings.
# ==============================================================================

# Create the declarative base class for our models
Base = declarative_base()

class Match(Base):
    """
    Match database model representing a verified face recognition event.
    """
    __tablename__ = 'matches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_name = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    screenshot_path = Column(String, nullable=True)
    video_source = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)

    def to_dict(self) -> dict:
        """
        Converts the database Match object into a standard Python dictionary.
        This makes it easy to serialize to JSON for the frontend API.
        """
        return {
            "id": self.id,
            "person_name": self.person_name,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat() + "Z", # Append Z to indicate UTC
            "screenshot_path": self.screenshot_path,
            "video_source": self.video_source,
            "status": self.status
        }

# Configure SQLite database connection engine.
# - sqlite:/// specifies the SQLite protocol.
# - check_same_thread=False is needed because SQLite by default limits connections
#   to the single thread that created it. Since detection loops or web servers (FastAPI)
#   run in separate threads, we disable this check. SQLite handles concurrent reads safely.
database_url = f"sqlite:///{DB_SQLITE_PATH.absolute()}"
engine = create_engine(database_url, connect_args={"check_same_thread": False})

# Create a configured "Session" class to manage database transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize the database table on import.
# create_all checks if the table 'matches' already exists. If not, it runs the CREATE TABLE DDL.
Base.metadata.create_all(bind=engine)


def log_match(person_name: str, confidence: float, screenshot_path: str | None = None, video_source: str = "0", status: str = "pending") -> Match:
    """
    Inserts a verified face recognition detection event log into the SQLite database.
    
    Args:
        person_name (str): The name/identity of the detected missing person.
        confidence (float): The similarity/confidence score (0.0 to 1.0).
        screenshot_path (str, optional): File path where the frame snapshot is saved on disk.
        video_source (str): Identifier of the stream source (e.g., '0' for webcam, or video filename).
        status (str): Match approval status ('pending', 'approved', 'rejected').
        
    Returns:
        Match: The created database Match model instance.
    """
    session = SessionLocal()
    try:
        new_match = Match(
            person_name=person_name,
            confidence=confidence,
            screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
            video_source=str(video_source),
            status=status
        )
        session.add(new_match)
        session.commit()
        # Refresh the instance to load its database-generated ID and default timestamp
        session.refresh(new_match)
        return new_match
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_recent_matches(limit: int = 50) -> list:
    """
    Queries the database for the most recent match events, ordered by timestamp descending.
    
    Args:
        limit (int): Maximum number of log records to return. Defaults to 50.
        
    Returns:
        list: A list of dict representations of Match records.
    """
    session = SessionLocal()
    try:
        results = (
            session.query(Match)
            .order_by(Match.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [match.to_dict() for match in results]
    finally:
        session.close()


def delete_all_matches() -> int:
    """
    Deletes every row from the matches table.

    Returns:
        int: Number of rows deleted.
    """
    session = SessionLocal()
    try:
        count = session.query(Match).delete()
        session.commit()
        return count
    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()

def update_match_status(match_id: int, status: str) -> dict | None:
    """
    Updates the status of a specific match.
    
    Args:
        match_id (int): ID of the match.
        status (str): New status ('pending', 'approved', 'rejected').
        
    Returns:
        dict: The updated match as a dict, or None if not found.
    """
    session = SessionLocal()
    try:
        match = session.query(Match).filter(Match.id == match_id).first()
        if not match:
            return None
        match.status = status
        session.commit()
        session.refresh(match)
        return match.to_dict()
    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()
