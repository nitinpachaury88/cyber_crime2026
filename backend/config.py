import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:Nitin%402007@localhost:3306/cybertrace",
    )

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "b14ITfywMcNNSSd_IVfKymGHVe5ee-HM2ngeEszJWOM"
    )

    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720")
    )

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    CLIENT_ORIGIN: str = os.getenv("CLIENT_ORIGIN", "http://localhost:3306")


settings = Settings()