export async function POST(req) {
    try {
        const body = await req.json();

        const res = await fetch('http://localhost:5000/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (res.ok) {
            return new Response(JSON.stringify({ message: 'Subscribed successfully!' }), { status: 200 });
        } else {
            const error = await res.json();
            return new Response(JSON.stringify(error), { status: res.status });
        }
    } catch (error) {
        return new Response(JSON.stringify({ message: 'Internal Server Error' }), { status: 500 });
    }
}
