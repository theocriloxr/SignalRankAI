import uvicorn
import logging
from web.app import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_runner")

def main():
    logger.info("Starting isolated web runner...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
