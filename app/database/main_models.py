from sqlalchemy import Column, Integer, String, Float, ForeignKey, BigInteger, DECIMAL, DateTime, func, Boolean, \
    UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, primary_key=True, index=True)

    coefficient = Column(Float, default=1.0, nullable=False)


    keys = relationship("ApiKey", back_populates="owner")
    custom_prices = relationship("UserPrice", back_populates="user", cascade="all, delete-orphan")


class UserPrice(Base):
    __tablename__ = "user_prices"

    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    model_name = Column(String(50), ForeignKey("prices.model_name"), nullable=False, index=True)
    custom_cost = Column(DECIMAL(precision=15, scale=6), nullable=False)


    user = relationship("User", back_populates="custom_prices")
    model = relationship("Price")




    __table_args__ = (UniqueConstraint('user_telegram_id', 'model_name', name='_user_model_uc'),)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_value = Column(String(100), unique=True, index=True, nullable=False)
    balance = Column(DECIMAL(precision=15, scale=6), default=0.0, nullable=False)

    owner_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

    owner = relationship("User", back_populates="keys")



class Price(Base):
    __tablename__ = "prices"

    model_name = Column(String(50), primary_key=True, index=True)
    cost = Column(DECIMAL(precision=15, scale=6), nullable=False)
    prime_cost = Column(DECIMAL(precision=15, scale=6), default=0.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now())
    admin_key_id = Column(Integer, nullable=False)
    action = Column(String(255), nullable=False)