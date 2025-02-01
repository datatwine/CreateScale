document.addEventListener("DOMContentLoaded", function () {
    let images = document.querySelectorAll(".background-slider img");
    let index = 0;

    function changeImage() {
        images.forEach(img => img.classList.remove("active")); // Remove active class from all
        images[index].classList.add("active"); // Show the current image
        index = (index + 1) % images.length; // Move to the next image in a loop
    }

    if (images.length > 0) {
        images[0].classList.add("active"); // Show first image immediately
        setInterval(changeImage, 4000); // Rotate images every 4 seconds
    }
});

