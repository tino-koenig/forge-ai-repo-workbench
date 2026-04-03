export async function loadUser(userId: string) {
    const response = await fetch(`/api/users/${userId}`);
    if (!response.ok) {
        throw new Error("request failed");
    }
    return response.json();
}
