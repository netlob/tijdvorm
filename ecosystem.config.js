module.exports = {
  apps: [
    {
      name: "tijdvorm-backend",
      script: "./venv/bin/uvicorn",
      args: "backend.server:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      env: {
        PYTHONPATH: ".",
        BACKEND_HOST: "0.0.0.0",
        BACKEND_PORT: "8000",
      },
    },
    {
      name: "tijdvorm-tv",
      script: "backend/main.py",
      interpreter: "./venv/bin/python",
      interpreter_args: "-u",
      env: {
        PYTHONPATH: ".",
      },
    },
    {
      name: "tijdvorm-frontend",
      cwd: "./frontend",
      script: "npm",
      args: "run dev",
      interpreter: "none",
      env: {
        HOST: "0.0.0.0",
        PORT: "5173",
      },
    },
  ],
};
