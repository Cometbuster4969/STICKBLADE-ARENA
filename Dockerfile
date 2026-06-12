# STICKBLADE ARENA — deployment image (Hugging Face Spaces / Render / Railway)
FROM python:3.12-slim

# SDL needs a few system libs even in dummy-video mode
RUN apt-get update && apt-get install -y --no-install-recommends \    
    libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 libsdl2-mixer-2.0-0 \    
    fontconfig fonts-dejavu-core \    
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Point to the subfolder for requirements
COPY stickblade/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the rest of the engine out of the subfolder
COPY stickblade/ .

ENV SDL_VIDEODRIVER=dummy \    
    PYTHONUNBUFFERED=1

# HF Spaces routes traffic to port 7860 by convention
EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]