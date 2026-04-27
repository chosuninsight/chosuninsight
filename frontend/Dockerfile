# Use an official Node runtime as a parent image
FROM node:20-alpine

# Set the working directory in the container
WORKDIR /app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package*.json ./

# Install project dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 5173

# Define the command to run the app
# Run dev server (Vite will load .env at runtime)
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
