FROM python:3.12-alpine
WORKDIR /app
COPY app.py .
EXPOSE 8096
CMD ["python", "app.py"]