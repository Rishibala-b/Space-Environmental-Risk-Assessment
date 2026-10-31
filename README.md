# Space Environmental Risk Assessment

An AI-powered Space Environmental Risk Assessment system built with React and FastAPI, integrating live Space-Track data and Machine Learning for satellite observation, space object classification, and orbital debris analysis, featuring interactive 3D visualization using CesiumJS and satellite.js.

# Tech Stack

## Frontend

* React.js
* JavaScript
* HTML
* CSS
* Vite
* CesiumJS
* satellite.js

## Backend

* Python
* FastAPI
* Uvicorn
* REST API

## Machine Learning

* Gradient Boosting Classifier
* Scikit-learn
* SMOTE (Synthetic Minority Over-sampling Technique)

## Data Source

* Space-Track.org
* Celestrak.org
* Two-Line Element (TLE) Data
* Satellite Orbital Parameters

## Tools

* VS Code
* Git & GitHub
* Vercel (Frontend Deployment)
* Render (Backend Deployment)

# Core Features & Use Cases

## 1. Satellite Observation Agent

* Retrieves live satellite orbital data from Space-Track.org.
* Processes Two-Line Element (TLE) information.
* Extracts orbital parameters such as inclination, eccentricity, and mean motion.
* Analyzes satellite information and provides observation details.

## 2. Space Object Classification Agent

* Classifies space objects using a trained Gradient Boosting model.
* Identifies objects as satellites or orbital debris.
* Uses orbital features for machine learning-based classification.
* Provides classification results and confidence scores.

## 3. Batch Analysis

* Analyzes multiple space objects in a single request.
* Processes objects in batches for efficient analysis.
* Generates classification results and summary statistics.
* Supports batch event analysis.

## 4. Interactive 3D Space Visualization

* Visualizes satellites and debris in an interactive 3D environment.
* Uses CesiumJS for globe rendering and satellite.js for orbital calculations.
* Displays satellites and debris with different visual markers.
* Provides orbital information and object details.

## 5. Live Orbital Data Integration

* Connects directly to Space-Track.org.
* Retrieves current orbital information for requested objects.
* Supports NORAD Catalog IDs and TLE-based inputs.
* Processes live data for observation and classification.

# System Architecture

The application follows a frontend-backend architecture:

* **Frontend:** React and Vite handle the user interface and visualization.
* **Backend:** FastAPI manages API requests and agent execution.
* **Data Source:** Space-Track.org provides live orbital data.
* **Machine Learning:** Gradient Boosting model performs space object classification.
* **Visualization:** CesiumJS and satellite.js provide interactive orbital visualization.

# Repository Structure

```text
Space-Environmental-Risk-Assessment/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── batch_agent.py
│   │   │   ├── classification_agent.py
│   │   │   └── observation_agent.py
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py
│   │   │
│   │   ├── services/
│   │   │   ├── classification_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── spacetrack_service.py
│   │   │   └── tle_service.py
│   │   │
│   │   ├── utils/
│   │   │   └── config.py
│   │   │
│   │   └── main.py
│   │
│   ├── data/
│   │   ├── gradient_boosting_model.pkl
│   │   └── README.md
│   │
│   ├── tests/
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── context/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   │
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.js
│
└── README.md
```

# Installation & Setup

## Prerequisites

* Python 3.10+
* Node.js and npm
* Git
* VS Code

## 1. Clone the Repository

```bash
git clone https://github.com/Rishibala-b/Space-Environmental-Risk-Assessment.git

cd Space-Environmental-Risk-Assessment
```

## 2. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate the environment (Windows):

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 3. Environment Configuration

Create a `.env` file inside the backend directory.

Configure the required credentials:

```env
SPACETRACK_USERNAME=your_spacetrack_username
SPACETRACK_PASSWORD=your_spacetrack_password
```

Add other environment variables if required by your backend configuration.

Never upload your actual credentials to GitHub.

## 4. Run the Backend

From the backend directory:

```bash
uvicorn app.main:app --reload
```

Backend API:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

## 5. Frontend Setup

Open another terminal and navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the local URL provided by Vite in your browser.

# Environment Variables

The backend requires Space-Track credentials to retrieve live orbital data.

| Variable            | Description                  |
| ------------------- | ---------------------------- |
| SPACETRACK_USERNAME | Space-Track account username |
| SPACETRACK_PASSWORD | Space-Track account password |

Keep the `.env` file private and use `.env.example` as a configuration template.

# Deployment

The application uses separate deployment platforms for the frontend and backend.

* **Frontend:** Vercel
* **Backend:** Render

The frontend communicates with the deployed FastAPI backend through API endpoints.

Configure the required environment variables in the backend deployment settings before running the application.

# License

This project is developed for educational, research, and learning purposes.
