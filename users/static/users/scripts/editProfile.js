document.addEventListener("DOMContentLoaded", function () {
    console.log("editProfile.js loaded and running!");

    // Ensure profile picture elements exist before adding event listeners
    const profilePic = document.getElementById("profile-pic");
    const profilePicUpload = document.getElementById("profile-pic-upload");

    if (profilePic && profilePicUpload) {
        profilePic.addEventListener("click", function () {
            profilePicUpload.click();
        });

        profilePicUpload.addEventListener("change", function () {
            document.getElementById("profile-form").submit();
        });
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
});
