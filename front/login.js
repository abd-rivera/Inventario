const API_BASE = "/api";

const loginTab = document.getElementById("loginTab");
const registerTab = document.getElementById("registerTab");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginError = document.getElementById("loginError");
const registerError = document.getElementById("registerError");

const loginUsername = document.getElementById("loginUsername");
const loginPassword = document.getElementById("loginPassword");
const registerUsername = document.getElementById("registerUsername");
const registerPassword = document.getElementById("registerPassword");
const registerPasswordConfirm = document.getElementById("registerPasswordConfirm");

// Check if already logged in
const token = localStorage.getItem("authToken");
if (token) {
  window.location.href = "/";
}

// Inicializar formularios
loginForm.style.display = "flex";
registerForm.style.display = "none";

loginTab.addEventListener("click", () => {
  loginTab.classList.add("active");
  registerTab.classList.remove("active");
  loginForm.style.display = "flex";
  registerForm.style.display = "none";
  loginError.textContent = "";
  registerError.textContent = "";
});

registerTab.addEventListener("click", () => {
  registerTab.classList.add("active");
  loginTab.classList.remove("active");
  registerForm.style.display = "flex";
  loginForm.style.display = "none";
  loginError.textContent = "";
  registerError.textContent = "";
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  const username = loginUsername.value.trim();
  const password = loginPassword.value.trim();

  if (!username || !password) {
    loginError.textContent = "Please fill in all fields.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      loginError.textContent = data.error || "Login failed.";
      return;
    }

    localStorage.setItem("authToken", data.token);
    localStorage.setItem("username", data.username);
    window.location.href = "/";
  } catch (error) {
    console.error(error);
    loginError.textContent = "Cannot reach server.";
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerError.textContent = "";

  const username = registerUsername.value.trim();
  const password = registerPassword.value.trim();
  const passwordConfirm = registerPasswordConfirm.value.trim();

  if (!username || !password || !passwordConfirm) {
    registerError.textContent = "Please fill in all fields.";
    return;
  }

  if (password !== passwordConfirm) {
    registerError.textContent = "Passwords do not match.";
    return;
  }

  if (password.length < 4) {
    registerError.textContent = "Password must be at least 4 characters.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      registerError.textContent = data.error || "Registration failed.";
      return;
    }

    localStorage.setItem("authToken", data.token);
    localStorage.setItem("username", data.username);
    window.location.href = "/";
  } catch (error) {
    console.error(error);
    registerError.textContent = "Cannot reach server.";
  }
});
