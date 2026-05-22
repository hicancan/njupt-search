import { useState, useEffect } from 'react';
import { APP_CONFIG } from '@/constants';

export function useDataUpdateNotifier() {
    const [newDataAvailable, setNewDataAvailable] = useState(false);

    useEffect(() => {
        if (!('BroadcastChannel' in window)) {
            return;
        }

        const channel = new BroadcastChannel(APP_CONFIG.UPDATE_CHANNEL);
        
        channel.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'CACHE_UPDATED') {
                console.log('SWR: New data cached in background.', event.data.payload);
                setNewDataAvailable(true);
            }
        });

        return () => {
            channel.close();
        };
    }, []);

    const reloadToUpdate = () => {
        window.location.reload();
    };

    return { newDataAvailable, reloadToUpdate };
}
