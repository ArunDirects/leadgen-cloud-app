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
    message.innerText = "Please enter email and password.";
    return;
  }

  const { data, error } = await supabase.auth.signUp({
    email,
    password
  });

  if (error) {
    message.innerText = error.message;
    return;
  }

  if (data.user) {
    await supabase.from("user_access").insert([
      {
        user_id: data.user.id,
        email: email,
        status: "pending"
      }
    ]);
  }

  message.innerText =
    "Your signup request has been submitted. Please wait for admin approval.";
}

async function loginUser() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const message = document.getElementById("message");

  if (!email || !password) {
    message.innerText = "Please enter email and password.";
    return;
  }

  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password
  });

  if (error) {
    message.innerText = error.message;
    return;
  }

  const user = data.user;

  const { data: accessData, error: accessError } = await supabase
    .from("user_access")
    .select("status")
    .eq("user_id", user.id)
    .single();

  if (accessError || !accessData) {
    message.innerText = "Access request not found.";
    return;
  }

  if (accessData.status === "approved") {
    window.location.href = "index.html";
  } else {
    message.innerText = "Your account is still pending approval.";
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

  if (error || !accessData || accessData.status !== "approved") {
    document.body.innerHTML = `
      <div style="font-family: Arial; padding: 40px;">
        <h2>Access Pending</h2>
        <p>Your account is not approved yet.</p>
        <button onclick="logoutUser()">Logout</button>
      </div>
    `;
    return;
  }

  document.getElementById("app").style.display = "block";
}

async function logoutUser() {
  await supabase.auth.signOut();
  window.location.href = "login.html";
}
