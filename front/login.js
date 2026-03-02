const API_BASE = "/api";

const loginTab = document.getElementById("loginTab");
const registerTab = document.getElementById("registerTab");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const verifyForm = document.getElementById("verifyForm");
const loginError = document.getElementById("loginError");
const registerError = document.getElementById("registerError");
const verifyError = document.getElementById("verifyError");

const loginUsername = document.getElementById("loginUsername");
const loginPassword = document.getElementById("loginPassword");
const registerUsername = document.getElementById("registerUsername");
const registerEmail = document.getElementById("registerEmail");
const registerPassword = document.getElementById("registerPassword");
const registerPasswordConfirm = document.getElementById("registerPasswordConfirm");
const verifyEmail = document.getElementById("verifyEmail");
const verifyCode = document.getElementById("verifyCode");
const resendCodeBtn = document.getElementById("resendCodeBtn");

let pendingVerificationEmail = "";

async function readApiPayload(response) {
  const raw = await response.text();
  try {
    return JSON.parse(raw || "{}");
  } catch {
    return { error: raw || `HTTP ${response.status}` };
  }
}

function clearErrors() {
  loginError.textContent = "";
  registerError.textContent = "";
  verifyError.textContent = "";
}

function showLogin() {
  loginTab.classList.add("active");
  registerTab.classList.remove("active");
  loginForm.style.display = "flex";
  registerForm.style.display = "none";
  verifyForm.style.display = "none";
  clearErrors();
}

function showRegister() {
  registerTab.classList.add("active");
  loginTab.classList.remove("active");
  registerForm.style.display = "flex";
  loginForm.style.display = "none";
  verifyForm.style.display = "none";
  clearErrors();
}

function showVerify(email) {
  pendingVerificationEmail = String(email || "").trim().toLowerCase();
  verifyEmail.value = pendingVerificationEmail;
  verifyCode.value = "";
  loginTab.classList.remove("active");
  registerTab.classList.remove("active");
  loginForm.style.display = "none";
  registerForm.style.display = "none";
  verifyForm.style.display = "flex";
  clearErrors();
}

// Check if already logged in
const token = localStorage.getItem("authToken");
if (token) {
  window.location.href = "/";
}

// Inicializar formularios
showLogin();

loginTab.addEventListener("click", () => {
  showLogin();
});

registerTab.addEventListener("click", () => {
  showRegister();
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

    const data = await readApiPayload(response);

    if (!response.ok) {
      if (response.status === 403 && data.code === "EMAIL_NOT_VERIFIED" && data.email) {
        showVerify(data.email);
        if (data.devCode) {
          verifyError.textContent = `Modo local: usa este código ${data.devCode}`;
        } else {
          verifyError.textContent = data.error || "Tu correo no está verificado. Te enviamos un nuevo código.";
        }
        return;
      }
      loginError.textContent = data.error || "Login failed.";
      return;
    }

    localStorage.setItem("authToken", data.token);
    localStorage.setItem("username", data.username);
    window.location.href = "/";
  } catch (error) {
    console.error(error);
    loginError.textContent = "No se pudo conectar con el servidor.";
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerError.textContent = "";

  const username = registerUsername.value.trim();
  const email = registerEmail.value.trim().toLowerCase();
  const password = registerPassword.value.trim();
  const passwordConfirm = registerPasswordConfirm.value.trim();

  if (!username || !email || !password || !passwordConfirm) {
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
      body: JSON.stringify({ username, email, password }),
    });

    const data = await readApiPayload(response);

    if (!response.ok) {
      registerError.textContent = data.error || "Registration failed.";
      return;
    }

    if (data.requiresVerification) {
      showVerify(data.email || email);
      if (data.devCode) {
        verifyError.textContent = `Modo local: usa este código ${data.devCode}`;
      } else {
        verifyError.textContent = "Revisa tu correo e ingresa el código de verificación.";
      }
      return;
    }

    registerError.textContent = "Cuenta creada, pero falta validación por correo.";
  } catch (error) {
    console.error(error);
    registerError.textContent = "No se pudo conectar con el servidor.";
  }
});

verifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  verifyError.textContent = "";

  const email = verifyEmail.value.trim().toLowerCase();
  const code = verifyCode.value.trim();

  if (!email || !code) {
    verifyError.textContent = "Email and code are required.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    });

    const data = await readApiPayload(response);

    if (!response.ok) {
      verifyError.textContent = data.error || "Verification failed.";
      return;
    }

    localStorage.setItem("authToken", data.token);
    localStorage.setItem("username", data.username);
    window.location.href = "/";
  } catch (error) {
    console.error(error);
    verifyError.textContent = "No se pudo conectar con el servidor.";
  }
});

resendCodeBtn.addEventListener("click", async () => {
  verifyError.textContent = "";
  const email = (verifyEmail.value || pendingVerificationEmail).trim().toLowerCase();

  if (!email) {
    verifyError.textContent = "No verification email found.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/resend-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    const data = await readApiPayload(response);

    if (!response.ok) {
      if (response.status === 429 && typeof data.waitSeconds === "number") {
        verifyError.textContent = `Espera ${data.waitSeconds}s para reenviar.`;
        return;
      }
      verifyError.textContent = data.error || "Could not resend code.";
      return;
    }

    if (data.devCode) {
      verifyError.textContent = `Modo local: nuevo código ${data.devCode}`;
    } else {
      verifyError.textContent = "Código reenviado. Revisa tu correo.";
    }
  } catch (error) {
    console.error(error);
    verifyError.textContent = "No se pudo conectar con el servidor.";
  }
});
