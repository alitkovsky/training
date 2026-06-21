FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir garminconnect>=0.2.19 python-dotenv>=1.0.0 supabase>=2.0.0
CMD ["python", "garmin_api.py"]
