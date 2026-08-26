/**
 * TDD — written BEFORE the fix (issue #101).
 *
 * The presigned R2 PUT (step 2 of uploadMedia) was sending
 *   body: { uri, name, type }
 * which is the FormData.append() shorthand, NOT a valid raw PUT body. On a
 * standalone Android build OkHttp can't turn that object into file bytes, so
 * the signed PUT fails. The fix reads the file URI into a Blob and PUTs the
 * Blob (actual binary) instead.
 *
 * Run: npm test -- upload
 */

jest.mock("../config/api", () => ({ API_BASE_URL: "http://localhost:8000/api" }));

import { uploadMedia } from "../api/upload";

const PRESIGN_URL = "http://localhost:8000/api/users/me/uploads/presign/";
const CONFIRM_URL = "http://localhost:8000/api/users/me/uploads/";
const SIGNED_R2_URL = "https://r2.example.com/signed-put?sig=abc";
const FILE_URI = "file:///data/user/0/app/cache/photo.jpg";

// A stand-in for the binary Blob that fetch(fileUri).blob() produces.
const FAKE_BLOB = { __isBlob: true, size: 1234, type: "image/jpeg" };

/**
 * Route global.fetch by URL so one mock serves all three fetches uploadMedia
 * makes: presign (Django), file read (fileUri), and the R2 PUT.
 */
function installFetchMock({ presignStatus = 200, r2Status = 200 } = {}) {
    const calls = [];
    global.fetch = jest.fn(async (url, opts = {}) => {
        calls.push({ url, opts });

        if (url === PRESIGN_URL) {
            if (presignStatus === 501) {
                return { ok: false, status: 501, json: async () => ({}) };
            }
            return {
                ok: true,
                status: 200,
                json: async () => ({
                    url: SIGNED_R2_URL,
                    key: "uploads/photo.jpg",
                    content_type: "image/jpeg",
                }),
            };
        }

        // Reading the local file into a Blob.
        if (url === FILE_URI) {
            return { ok: true, status: 200, blob: async () => FAKE_BLOB };
        }

        if (url === SIGNED_R2_URL) {
            return { ok: r2Status < 400, status: r2Status, json: async () => ({}) };
        }

        if (url === CONFIRM_URL) {
            return {
                ok: true,
                status: 201,
                json: async () => ({ id: 7, caption: "hi" }),
            };
        }

        throw new Error(`unexpected fetch to ${url}`);
    });
    return calls;
}

const ARGS = {
    token: "tok",
    fileUri: FILE_URI,
    fileName: "photo.jpg",
    contentType: "image/jpeg",
    caption: "hi",
};

describe("uploadMedia — presigned R2 PUT", () => {
    afterEach(() => jest.resetAllMocks());

    test("PUTs a Blob (binary), not the { uri, name, type } object", async () => {
        const calls = installFetchMock();

        await uploadMedia(ARGS);

        const put = calls.find((c) => c.url === SIGNED_R2_URL);
        expect(put).toBeDefined();
        expect(put.opts.method).toBe("PUT");
        // The regression: body must be the Blob, never the RN shorthand object.
        expect(put.opts.body).toBe(FAKE_BLOB);
        expect(put.opts.body).not.toMatchObject({ uri: expect.anything() });
    });

    test("sends the signed content-type header on the PUT", async () => {
        const calls = installFetchMock();

        await uploadMedia(ARGS);

        const put = calls.find((c) => c.url === SIGNED_R2_URL);
        expect(put.opts.headers).toMatchObject({ "Content-Type": "image/jpeg" });
    });

    test("confirms with Django after a successful PUT", async () => {
        const calls = installFetchMock();

        const result = await uploadMedia(ARGS);

        const confirm = calls.find((c) => c.url === CONFIRM_URL);
        expect(confirm).toBeDefined();
        expect(JSON.parse(confirm.opts.body)).toEqual({
            key: "uploads/photo.jpg",
            caption: "hi",
        });
        expect(result).toEqual({ id: 7, caption: "hi" });
    });

    test("throws a clear error when the file can't be read into a Blob", async () => {
        global.fetch = jest.fn(async (url) => {
            if (url === PRESIGN_URL) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        url: SIGNED_R2_URL,
                        key: "uploads/photo.jpg",
                        content_type: "image/jpeg",
                    }),
                };
            }
            if (url === FILE_URI) {
                return { ok: true, status: 200, blob: async () => {
                    throw new Error("boom");
                } };
            }
            throw new Error(`unexpected fetch to ${url}`);
        });

        await expect(uploadMedia(ARGS)).rejects.toThrow(/could not read file/i);
    });

    test("throws when the R2 PUT fails", async () => {
        installFetchMock({ r2Status: 403 });

        await expect(uploadMedia(ARGS)).rejects.toThrow(/R2 upload failed: 403/);
    });

    test("still falls back to legacy multipart on presign 501 (unchanged)", async () => {
        const calls = installFetchMock({ presignStatus: 501 });

        await uploadMedia(ARGS);

        // No R2 PUT and no Blob read on the legacy path.
        expect(calls.find((c) => c.url === SIGNED_R2_URL)).toBeUndefined();
        expect(calls.find((c) => c.url === FILE_URI)).toBeUndefined();
        // Legacy path POSTs FormData straight to the confirm endpoint.
        const legacy = calls.find((c) => c.url === CONFIRM_URL);
        expect(legacy).toBeDefined();
        expect(legacy.opts.body).toBeInstanceOf(FormData);
    });
});
