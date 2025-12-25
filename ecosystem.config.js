module.exports = {
  apps: [
    {
      name: "tijdvorm-backend",
      script: "backend/server.py",
      interpreter: "./venv/bin/python",
      interpreter_args: "-u", // Unbuffered output for real-time logs
      env: {
        PYTHONPATH: ".",
        BACKEND_HOST: "0.0.0.0",
        BACKEND_PORT: "8000"
      }
    },
    {
      name: "tijdvorm-tv",
      script: "backend/main.py",
      interpreter: "./venv/bin/python",
      interpreter_args: "-u",
      env: {
        PYTHONPATH: "."
      }
    },
    {
      name: "tijdvorm-frontend",
      cwd: "./frontend",
      script: "npm",
      args: "run dev",
      interpreter: "none",
      env: {
        HOST: "0.0.0.0",
        PORT: "5173"
      }
    }
  ]
};
