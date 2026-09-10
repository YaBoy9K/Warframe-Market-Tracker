FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY market_tracker.py mission_tracker.py ./
COPY watchlist.json watchlist-all-ducat-deals.json watchlist-1p-frequent.json ./

CMD ["python", "-u", "market_tracker.py"]
