const SUPABASE_URL = "https://adaakgiddzplucwtnvch.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkYWFrZ2lkZHpwbHVjd3RudmNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyMjc4ODQsImV4cCI6MjA5MzgwMzg4NH0.0r4amrnlTY0MV0hItsxqIg20LN_V_evmV734xOwIqPg";

const supabase = window.supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);

async function signupUser() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message = document.getElementById("message");

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

  const { data, error } = await supabase.auth.signUp({
    email,
    password
  });

  if (error) {
    message.style.color = "#d92d20";
    message.innerText = error.message;
    return;
  }

  // data.user exists even before email confirmation.
  // Insert into user_access immediately so admin can see & approve the request.
  if (data.user) {
    const { error: insertError } = await supabase.from("user_access").insert([
      {
        user_id: data.user.id,
        email: email,
        status: "pending"
      }
    ]);

    if (insertError) {
      // Duplicate signup — user already exists
      if (insertError.code === "23505") {
        message.style.color = "#d92d20";
        message.innerText = "This email has already submitted a request. Please wait for approval or contact the admin.";
      } else {
        message.style.color = "#d92d20";
        message.innerText = "Request recorded, but could not save to approval queue: " + insertError.message;
      }
      return;
    }
  }

  message.style.color = "#00a96e";
  message.innerText =
    "✅ Request submitted! Please check your email and confirm your address, then wait for admin approval before logging in.";
}

async function loginUser() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message = document.getElementById("message");

  if (!email || !password) {
    message.style.color = "#d92d20";
    message.innerText = "Please enter email and password.";
    return;
  }

  message.style.color = "#69758c";
  message.innerText = "Checking login...";

  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password
  });

  if (error) {
    message.style.color = "#d92d20";
    // Make "Email not confirmed" friendlier
    if (error.message.toLowerCase().includes("email not confirmed")) {
      message.innerText = "Please confirm your email address first. Check your inbox for a confirmation link.";
    } else if (error.message.toLowerCase().includes("invalid login")) {
      message.innerText = "Incorrect email or password.";
    } else {
      message.innerText = error.message;
    }
    return;
  }

  const user = data.user;

  const { data: accessData, error: accessError } = await supabase
    .from("user_access")
    .select("status")
    .eq("user_id", user.id)
    .single();

  if (accessError || !accessData) {
    message.style.color = "#d92d20";
    message.innerText = "Access request not found. Please sign up first.";
    return;
  }

  if (accessData.status === "approved") {
    window.location.href = "index.html";
  } else if (accessData.status === "rejected") {
    message.style.color = "#d92d20";
    message.innerText = "Your access request has been rejected. Please contact the admin.";
  } else {
    message.style.color = "#b65c00";
    message.innerText = "⏳ Your account is pending admin approval. You'll be able to log in once approved.";
  }
}

async function checkAccess() {
  const { data } = await supabase.auth.getSession();

  if (!data.session) {
    window.location.href = "login.html";
    return;
  }

  const user = data.session.user;

  const { data: accessData, error } = await supabase
    .from("user_access")
    .select("status")
    .eq("user_id", user.id)
    .single();

  if (error || !accessData) {
    // No access record — sign out and redirect
    await supabase.auth.signOut();
    window.location.href = "login.html";
    return;
  }

  if (accessData.status !== "approved") {
    // Sign them out so stale session doesn't persist
    await supabase.auth.signOut();
    document.body.innerHTML = `
      <div style="font-family:'DM Sans',Arial,sans-serif;padding:40px;max-width:480px;margin:80px auto;background:#fff;border:1px solid #e2e6f0;border-radius:16px;box-shadow:0 8px 30px rgba(20,30,50,.08);text-align:center;">
        <div style="font-size:40px;margin-bottom:16px;">${accessData.status === "rejected" ? "🚫" : "⏳"}</div>
        <h2 style="margin:0 0 10px;color:#162033;">${accessData.status === "rejected" ? "Access Denied" : "Approval Pending"}</h2>
        <p style="color:#69758c;margin:0 0 24px;">
          ${accessData.status === "rejected"
            ? "Your access request has been rejected. Please contact the admin."
            : "Your account is awaiting admin approval. You will be able to log in once approved."}
        </p>
        <a href="login.html" style="display:inline-block;padding:10px 24px;background:#00a96e;color:#fff;text-decoration:none;border-radius:10px;font-weight:700;">Back to Login</a>
      </div>
    `;
    return;
  }

  if (typeof startProtectedApp === "function") {
    startProtectedApp();
  } else {
    document.getElementById("app").style.display = "block";
  }
}

async function logoutUser() {
  await supabase.auth.signOut();
  window.location.href = "login.html";
}
