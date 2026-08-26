// src/utils/mediaViewer.js
//
// Pure helper shared by ProfileScreen (own profile) and ProfileDetailScreen
// (another user's profile): turns an Upload record into the pre-resolved
// { uri, isVideo, caption, id } shape MediaViewer expects.
//
// resolveUrl is the caller's own makeMediaUrl (each screen has its own copy
// that knows the API base), so this stays free of config concerns and is
// trivially testable. An image always wins over a video when both are present,
// matching how the grid thumbnails already decide what to show.

export function buildMediaSource(upload, resolveUrl) {
    if (!upload) return null;

    const imageUrl = resolveUrl(upload.image_url || upload.image);
    const videoUrl = resolveUrl(upload.video_url || upload.video);
    const uri = imageUrl || videoUrl;
    if (!uri) return null;

    return {
        uri,
        isVideo: !imageUrl && !!videoUrl,
        caption: upload.caption || "",
        id: upload.id,
    };
}
