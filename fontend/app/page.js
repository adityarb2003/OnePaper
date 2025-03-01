'use client';

import { useState } from 'react';
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Newspaper, Loader2 } from "lucide-react"


export default function Page() {
    const [email, setEmail] = useState('');
    const [preferences, setPreferences] = useState([]);
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);


    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);

        try {
            const res = await fetch('/api/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, preferences }),
            });

            if (res.ok) {
                setMessage('✨ Successfully subscribed!');
                setEmail('');
                setPreferences([]);
            } else {
                const errorData = await res.json();
                setMessage(`Error: ${errorData.message || 'Subscription failed.'}`);
            }
        } catch (error) {
            setMessage('Error: Unable to connect to the server.');
        } finally {
            setIsLoading(false);
        }
    };

    const togglePreference = (preference) => {
        setPreferences((prev) =>
            prev.includes(preference)
                ? prev.filter((pref) => pref !== preference)
                : [...prev, preference]
        );
    };

    // const newsources = [
    //     'Hacker News',
    //     'Reddit Tech',
    //     'Dev.to',
    //     'GitHub Trending',
    //     'Stack Exchange',
    //     'The Verge',
    //     'Wired',
    //     'Ars Technica',
    //     'VentureBeat',
    //     'ZDNet',
    //     'TechRadar',
    //     'Hackernoon',
    // ];
    const newsources = [
        'Programming',
        'Tech & AI',
    ];

    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
            <Card className="w-full max-w-2xl">
                <CardHeader className="text-center">
                    <div className="flex items-center justify-center space-x-2">
                        <Newspaper className="h-6 w-6" />
                        <CardTitle className="text-3xl font-bold">OnePaper Newsletters</CardTitle>
                    </div>
                    <CardDescription className="text-center">
                        Stay up to date with the latest tech news from your favorite sources
                    </CardDescription>
                </CardHeader>

                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-6">
                        {message && (
                            <Alert variant={message.includes('Error') ? 'destructive' : 'default'}>
                                <AlertDescription>{message}</AlertDescription>
                            </Alert>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="email">Email address</Label>
                            <Input
                                id="email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="Enter your email"
                                className="w-full"
                                required
                            />
                        </div>

                        <div className="space-y-4">
                            {/* <Label>Select your news sources</Label> */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {newsources.map((source) => (
                                    <div key={source} className="flex items-center space-x-2">
                                        <Checkbox
                                            id={source}
                                            checked={preferences.includes(source)}
                                            onCheckedChange={() => togglePreference(source)}
                                        />
                                        <Label
                                            htmlFor={source}
                                            className="text-sm font-sans cursor-pointer"
                                        >
                                            {source}
                                        </Label>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </CardContent>

                    <CardFooter>
                        <Button
                            type="submit"
                            className="w-full"
                            disabled={!email || isLoading}
                        >
                            {isLoading ? (
                                <span className="flex items-center justify-center">
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Subscribing...
                                </span>
                            ) : (
                                'Subscribe to Newsletter'
                            )}
                        </Button>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
}