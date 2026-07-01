# Orchestra AI

Orchestra AI is an AI Engineering Studio designed to transform a raw product idea or business requirements prompt into a complete, deployment-ready software engineering blueprint. Using collaborating specialized AI agents managed by a central conductor, the platform delivers structural requirements, architectures, schemas, API specifications, and infrastructure definitions.

---

## Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Docker (optional, required for local Sandbox execution)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/orchestra_ai.git
cd orchestra_ai
```

### 2. Create and Activate a Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
On macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install the package and core dependencies:
```bash
pip install -e .
```
Or install directly via `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Running the Studio
Once implementation is complete, run the studio server using:
```bash
uvicorn app.main:app --reload
```
The FastAPI web server will bootstrap and start listening on `http://127.0.0.1:8000`.
