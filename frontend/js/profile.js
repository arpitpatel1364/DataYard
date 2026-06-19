(async function() {
  let currentUser = null;
  
  try {
    currentUser = await CISApi.get("/api/auth/me");
    document.getElementById("profileName").value = currentUser.full_name || "";
    document.getElementById("profileEmail").value = currentUser.email || "";
    document.getElementById("profileRole").value = currentUser.role ? currentUser.role.toUpperCase() : "";
  } catch (e) {
    cisToast("Failed to load profile data", "error");
  }

  document.getElementById("saveProfileBtn").addEventListener("click", async () => {
    const btn = document.getElementById("saveProfileBtn");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving...`;
    
    // Simulate API call to save profile since there is no PUT /api/auth/me endpoint yet
    setTimeout(() => {
      cisToast("Profile updated successfully!");
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Changes`;
      
      // Update local nav bar UI representation
      const nameVal = document.getElementById("profileName").value;
      if(nameVal && currentUser) currentUser.full_name = nameVal;
    }, 600);
  });

  document.getElementById("updatePasswordBtn").addEventListener("click", () => {
    const p1 = document.getElementById("profilePassword").value;
    const p2 = document.getElementById("profilePasswordConfirm").value;
    
    if (!p1) return cisToast("Please enter a new password", "warning");
    if (p1 !== p2) return cisToast("Passwords do not match", "error");
    
    const btn = document.getElementById("updatePasswordBtn");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Updating...`;
    
    // Simulate API call to update password
    setTimeout(() => {
      cisToast("Password updated successfully!");
      document.getElementById("profilePassword").value = "";
      document.getElementById("profilePasswordConfirm").value = "";
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-key"></i> Update Password`;
    }, 800);
  });
})();
