from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime, func, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    company_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True))

    case_studies = relationship('CaseStudy', back_populates='user')




class CaseStudy(Base):
    __tablename__ = 'case_studies'
    id = Column(Integer, primary_key=True)  # Auto int PK for each case study
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(200))
    final_summary = Column(Text)       # Final aggregated summary for the whole case
    final_summary_pdf_path = Column(String(500))  # ✅ Add this line
    meta_data_text = Column(Text, nullable=True)  # <-- Added for meta data storage
    linkedin_post = Column(Text, nullable=True)  # Store the generated LinkedIn post
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # HeyGen video fields
    video_id = Column(String(100), nullable=True)  # Store HeyGen video ID
    video_url = Column(Text, nullable=True)  # Store video URL
    video_status = Column(String(50), nullable=True)  # Store video generation status
    video_created_at = Column(DateTime(timezone=True), nullable=True)  # When video was created

    user = relationship('User', back_populates='case_studies')
    solution_provider_interview = relationship('SolutionProviderInterview', uselist=False, back_populates='case_study')
    client_interview = relationship('ClientInterview', uselist=False, back_populates='case_study')
    invite_tokens = relationship('InviteToken', back_populates='case_study')
    labels = relationship('Label', secondary='case_study_labels', back_populates='case_studies')


class SolutionProviderInterview(Base):
    __tablename__ = 'solution_provider_interviews'
    id = Column(Integer, primary_key=True)
    case_study_id = Column(Integer, ForeignKey('case_studies.id', ondelete='CASCADE'), nullable=False, unique=True)
    session_id = Column(String(36), unique=True, nullable=False)  # UUID for the session, optional but recommended
    transcript = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    client_link_url = Column(String(500), nullable=True)

    case_study = relationship('CaseStudy', back_populates='solution_provider_interview')


class ClientInterview(Base):
    __tablename__ = 'client_interviews'
    id = Column(Integer, primary_key=True)
    case_study_id = Column(Integer, ForeignKey('case_studies.id', ondelete='CASCADE'), nullable=False, unique=True)
    session_id = Column(String(36), unique=True, nullable=False)  # UUID for client interview session
    transcript = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case_study = relationship('CaseStudy', back_populates='client_interview')


class InviteToken(Base):
    __tablename__ = 'invite_tokens'
    id = Column(Integer, primary_key=True)
    case_study_id = Column(Integer, ForeignKey('case_studies.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(36), unique=True, nullable=False)  # Client invite token
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case_study = relationship('CaseStudy', back_populates='invite_tokens')


# Association table for many-to-many relationship between CaseStudy and Label
case_study_labels = Table(
    'case_study_labels', Base.metadata,
    Column('case_study_id', Integer, ForeignKey('case_studies.id', ondelete='CASCADE'), primary_key=True),
    Column('label_id', Integer, ForeignKey('labels.id', ondelete='CASCADE'), primary_key=True)
)

class Label(Base):
    __tablename__ = 'labels'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship('User')
    case_studies = relationship('CaseStudy', secondary=case_study_labels, back_populates='labels')

class Feedback(Base):
    __tablename__ = 'feedbacks'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False)
    rating = Column(Integer)  # Optional rating from 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    feedback_type = Column(String(50))  # e.g., 'feature', 'bug', 'improvement'
    status = Column(String(20), default='pending')  # pending, reviewed, addressed
    
    # Relationship with User
    user = relationship('User', backref='feedbacks')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'content': self.content,
            'rating': self.rating,
            'created_at': self.created_at.isoformat(),
            'feedback_type': self.feedback_type,
            'status': self.status
        }
