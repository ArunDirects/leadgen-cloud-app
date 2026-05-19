const SUPABASE_URL = "https://adaakgiddzplucwtnvch.supabase.co";

const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkYWFrZ2lkZHpwbHVjd3RudmNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyMjc4ODQsImV4cCI6MjA5MzgwMzg4NH0.0r4amrnlTY0MV0hItsxqIg20LN_V_evmV734xOwIqPg";

const supabaseClient = window.supabase.createClient(
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

  const { data, error } =
    await supabaseClient.auth.signUp({
      email,
      password
    });

  if (error) {
    message.style.color = "#d92d20";
    message.innerText = error.message;
    return;
  }

  if (data.user) {
    const { error: insertError } =
      await supabaseClient
        .from("user_access")
        .insert([
          {
            user_id: data.user.id,
            email: email,
            status: "pending"
          }
        ]);

    if (insertError) {
      message.style.color = "#d92d20";
      message.innerText =
        "Could not save approval request: " +
        insertError.message;
      return;
    }
  }

  message.style.color = "#00a96e";
  message.innerText =
    "✅ Request submitted successfully. Wait for admin approval.";
}

async function loginUser() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message = document.getElementById("message");

  if (!email || !password) {
    message.style.color = "#d92d20";
    message.innerText =
      "Please enter email and password.";
    return;
  }

  message.style.color = "#69758c";
  message.innerText = "Checking login...";

  const { data, error } =
    await supabaseClient.auth.signInWithPassword({
      email,
      password
    });

  if (error) {
    message.style.color = "#d92d20";
    message.innerText = error.message;
    return;
  }

  const user = data.user;

  const {
    data: accessData,
    error: accessError
  } = await supabaseClient
    .from("user_access")
    .select("status")
    .eq("user_id", user.id)
    .single();

  if (accessError || !accessData) {
    message.style.color = "#d92d20";
    message.innerText =
      "Access request not found.";
    return;
  }

  if (accessData.status === "approved") {
    window.location.href = "/";
  } else {
    message.style.color = "#b65c00";
    message.innerText =
      "Your account is pending approval.";
  }
}

async function checkAccess() {
  const { data } =
    await supabaseClient.auth.getSession();

  if (!data.session) {
    window.location.href = "/login.html";
    return;
  }

  const user = data.session.user;

  const {
    data: accessData,
    error
  } = await supabaseClient
    .from("user_access")
    .select("status")
    .eq("user_id", user.id)
    .single();

  if (error || !accessData) {
    await supabaseClient.auth.signOut();
    window.location.href = "/login.html";
    return;
  }

  if (accessData.status !== "approved") {
    await supabaseClient.auth.signOut();

    document.body.innerHTML = `
      <div style="font-family:Arial;padding:40px;text-align:center;">
        <h2>Approval Pending</h2>
        <p>Your account is awaiting admin approval.</p>
      </div>
    `;
    return;
  }

  if (typeof startProtectedApp === "function") {
    startProtectedApp();
  } else {
    document.getElementById("app").style.display =
      "block";
  }
}

async function logoutUser() {
  await supabaseClient.auth.signOut();
  window.location.href = "/login.html";
}
