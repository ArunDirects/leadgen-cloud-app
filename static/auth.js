const SUPABASE_URL = "https://adaakgiddzplucwtnvch.supabase.co";

const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkYWFrZ2lkZHpwbHVjd3RudmNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyMjc4ODQsImV4cCI6MjA5MzgwMzg4NH0.0r4amrnlTY0MV0hItsxqIg20LN_V_evmV734xOwIqPg";

const supabaseClient = window.supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);

// ── HELPER: get user access status safely (no 406) ────────────────────────
async function getUserStatus(userId) {
  try {
    const { data, error } = await supabaseClient
      .from("user_access")
      .select("status")
      .eq("user_id", userId)
      .maybeSingle(); // maybeSingle() returns null instead of 406 when no row found

    if (error) {
      console.error("getUserStatus error:", error.message);
      return null;
    }
    return data; // null if not found, { status: '...' } if found
  } catch (e) {
    console.error("getUserStatus exception:", e);
    return null;
  }
}

// ── SIGNUP ────────────────────────────────────────────────────────────────
async function signupUser() {
  const email    = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message  = document.getElementById("message");

  if (!email || !password) {
    message.style.color = "#d92d20";
    message.innerText = "Please enter email and password.";
    return;
  }

  if (password.length < 6) {
    message.style.color = "#d92d20";
    message.innerText = "Password must be at least 6 characters.";
    return;
  }

  message.style.color = "#69758c";
  message.innerText = "Submitting request...";

  const { data, error } = await supabaseClient.auth.signUp({ email, password });

  if (error) {
    message.style.color = "#d92d20";
    message.innerText = error.message;
    return;
  }

  if (data.user) {
    // Check if already exists before inserting
    const existing = await getUserStatus(data.user.id);

    if (!existing) {
      const { error: insertError } = await supabaseClient
        .from("user_access")
        .insert([{ user_id: data.user.id, email: email, status: "pending" }]);

      if (insertError) {
        console.error("Insert error:", insertError.message);
        // Don't block signup — admin can add manually
      }
    }
  }

  message.style.color = "#00a96e";
  message.innerText = "✅ Request submitted! You'll get access once the admin approves your account.";
}

// ── LOGIN ─────────────────────────────────────────────────────────────────
async function loginUser() {
  const email    = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message  = document.getElementById("message");

  if (!email || !password) {
    message.style.color = "#d92d20";
    message.innerText = "Please enter email and password.";
    return;
  }

  message.style.color = "#69758c";
  message.innerText = "Checking login...";

  const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });

  if (error) {
    message.style.color = "#d92d20";
    message.innerText = error.message;
    return;
  }

  const user = data.user;
  const accessData = await getUserStatus(user.id);

  if (!accessData) {
    // User exists in auth but not in user_access — try to insert as pending
    await supabaseClient
      .from("user_access")
      .insert([{ user_id: user.id, email: user.email, status: "pending" }])
      .select();

    await supabaseClient.auth.signOut();
    message.style.color = "#d92d20";
    message.innerText = "Your account is pending admin approval. You'll be notified once approved.";
    return;
  }

  if (accessData.status === "approved") {
    window.location.href = "/";
  } else if (accessData.status === "pending") {
    await supabaseClient.auth.signOut();
    message.style.color = "#b65c00";
    message.innerText = "⏳ Your account is pending admin approval.";
  } else {
    await supabaseClient.auth.signOut();
    message.style.color = "#d92d20";
    message.innerText = "❌ Your access request was not approved. Contact the admin.";
  }
}

// ── CHECK ACCESS (called on protected pages) ──────────────────────────────
async function checkAccess() {
  const { data } = await supabaseClient.auth.getSession();

  if (!data.session) {
    window.location.href = "/login.html";
    return;
  }

  const user = data.session.user;
  const accessData = await getUserStatus(user.id);

  if (!accessData) {
    await supabaseClient.auth.signOut();
    window.location.href = "/login.html";
    return;
  }

  if (accessData.status !== "approved") {
    await supabaseClient.auth.signOut();
    document.body.innerHTML = `
      <div style="font-family:'Outfit',Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f0f2f8;">
        <div style="background:#fff;border:1px solid #e4e8f2;border-radius:16px;padding:48px 40px;text-align:center;max-width:420px;box-shadow:0 4px 20px rgba(13,21,38,.08);">
          <div style="font-size:48px;margin-bottom:16px;">⏳</div>
          <h2 style="font-size:22px;font-weight:800;margin-bottom:10px;color:#0d1526;">Approval Pending</h2>
          <p style="color:#64718a;font-size:14px;line-height:1.6;margin-bottom:24px;">
            Your account is awaiting admin approval.<br/>You'll receive access once approved.
          </p>
          <a href="/login.html" style="color:#2563eb;font-size:13px;font-weight:600;text-decoration:none;">← Back to Login</a>
        </div>
      </div>`;
    return;
  }

  if (typeof startProtectedApp === "function") {
    startProtectedApp();
  } else {
    document.getElementById("app").style.display = "block";
  }
}

// ── LOGOUT ────────────────────────────────────────────────────────────────
async function logoutUser() {
  await supabaseClient.auth.signOut();
  window.location.href = "/login.html";
}
