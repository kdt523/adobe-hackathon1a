# --- Stage 1: Base Image ---
# Use an official, slim Python image. The --platform flag is critical
# to ensure compatibility with the hackathon's AMD64 judging environment.
FROM --platform=linux/amd64 python:3.9-slim

# --- Stage 2: Set Working Directory ---
# Set the default working directory inside the container to /app.
# This keeps the project organized and matches the hackathon's volume mount paths.
WORKDIR /app

# --- Stage 3: Install Dependencies ---
# Copy the requirements file first. This leverages Docker's layer caching,
# making subsequent builds much faster if your dependencies don't change.
COPY requirements.txt .

# Install the Python libraries listed in requirements.txt.
# The --no-cache-dir flag helps keep the final image size smaller.
# The libraries are downloaded during this build phase (when internet is allowed).
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 4: Copy Application Code ---
# Copy your Python solution script into the container's working directory.
COPY solution_1a.py .

# --- Stage 5: Define Execution Command ---
# Specify the command that will run when the container starts.
# This directly executes your Python script to process the files.
CMD ["python", "solution_1a.py"]