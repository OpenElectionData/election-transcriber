from transcriber.database import init_db
from transcriber.app_config import DB_CONN

if __name__ == "__main__":
    init_db()
    print "Done!"
