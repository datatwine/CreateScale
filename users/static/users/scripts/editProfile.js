document.addEventListener("DOMContentLoaded", function () {
    console.log("editProfile.js loaded and running!");

    // Ensure profile picture elements exist before adding event listeners
    const profilePic = document.getElementById("profile-pic");
    const profilePicUpload = document.getElementById("profile-pic-upload");

    if (profilePic && profilePicUpload) {
        profilePic.addEventListener("click", function () {
            profilePicUpload.click();
        });

        // profilePicUpload.addEventListener("change", function () {
        //     document.getElementById("profile-form").submit();
        // });
    }

    // Ensure bio editing elements exist
    const bioText = document.getElementById("bio-text");
    const bioInput = document.getElementById("bio-input");
    const editBioIcon = document.querySelector(".edit-bio");

    if (bioText && bioInput && editBioIcon) {
        editBioIcon.addEventListener("click", function () {
            bioText.style.display = "none";
            bioInput.style.display = "inline-block";
            bioInput.focus();
        });

        bioInput.addEventListener("blur", function () {
            if (bioInput.value.trim() !== "") {
                bioText.innerText = bioInput.value;
            }
            bioText.style.display = "inline-block";
            bioInput.style.display = "none";
        });
    }

    // Ensure location editing elements exist
    const locationText = document.getElementById("location-text");
    const locationInput = document.getElementById("location-input");
    const editLocationIcon = document.querySelector(".edit-location");

    if (locationText && locationInput && editLocationIcon) {
        editLocationIcon.addEventListener("click", function () {
            locationText.style.display = "none";
            locationInput.style.display = "inline-block";
            locationInput.focus();
        });

        locationInput.addEventListener("blur", function () {
            if (locationInput.value.trim() !== "") {
                locationText.innerText = locationInput.value;
            }
            locationText.style.display = "inline-block";
            locationInput.style.display = "none";
        });
    }

    document.querySelector(".edit-profession").addEventListener("click", function () {
        document.getElementById("profession-text").style.display = "none";
        document.getElementById("profession-input").style.display = "inline";
    });
});

/* ========== UPLOAD EDIT / DELETE ========== */

function _csrfToken() {
  return document.querySelector("[name=csrfmiddlewaretoken]").value;
}

function _card(el) {
  return el.closest(".upload-card");
}

/* --- Three-dot dropdown --- */

function toggleUploadMenu(btn) {
  event.stopPropagation();
  var dropdown = _card(btn).querySelector(".upload-menu-dropdown");
  // Close every other open menu first
  document.querySelectorAll(".upload-menu-dropdown.show").forEach(function (d) {
    if (d !== dropdown) d.classList.remove("show");
  });
  dropdown.classList.toggle("show");
}

// Click anywhere outside → close all menus
document.addEventListener("click", function () {
  document.querySelectorAll(".upload-menu-dropdown.show").forEach(function (d) {
    d.classList.remove("show");
  });
});

/* --- Edit caption --- */

function startEditCaption(btn) {
  var card = _card(btn);
  card.querySelector(".upload-menu-dropdown").classList.remove("show");
  card.querySelector(".card-overlay").style.display = "none";
  var editForm = card.querySelector(".upload-edit-form");
  editForm.style.display = "block";
  editForm.querySelector(".upload-edit-input").focus();
}

function cancelEditCaption(btn) {
  var card = _card(btn);
  card.querySelector(".upload-edit-form").style.display = "none";
  card.querySelector(".card-overlay").style.display = "";
}

function saveCaption(btn) {
  var card = _card(btn);
  var uploadId = card.dataset.uploadId;
  var textarea = card.querySelector(".upload-edit-input");
  var newCaption = textarea.value.trim();

  btn.disabled = true;
  btn.textContent = "Saving…";

  fetch("/api/users/me/uploads/" + uploadId + "/", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": _csrfToken(),
    },
    body: JSON.stringify({ caption: newCaption }),
  })
    .then(function (res) {
      if (!res.ok) throw new Error("Server returned " + res.status);
      return res.json();
    })
    .then(function (data) {
      // Update displayed caption text
      card.querySelector(".card-overlay .caption").textContent = data.caption || "";
      card.querySelector(".upload-edit-form").style.display = "none";
      card.querySelector(".card-overlay").style.display = "";
    })
    .catch(function (err) {
      alert("Could not save caption: " + err.message);
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Save";
    });
}

/* --- Delete upload --- */

function confirmDeleteUpload(btn) {
  if (!confirm("Delete this upload? This cannot be undone.")) return;

  var card = _card(btn);
  var uploadId = card.dataset.uploadId;

  fetch("/api/users/me/uploads/" + uploadId + "/", {
    method: "DELETE",
    headers: { "X-CSRFToken": _csrfToken() },
  })
    .then(function (res) {
      if (!res.ok) throw new Error("Server returned " + res.status);
      // Fade out then remove from DOM — grid reflows automatically
      card.classList.add("removing");
      setTimeout(function () { card.remove(); }, 300);
    })
    .catch(function (err) {
      alert("Could not delete upload: " + err.message);
    });
}

