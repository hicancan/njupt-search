import { APP_CONFIG } from '@/app/config/constants';

export const buildExamCalendarFilename = (className: string): string => {
    return `${APP_CONFIG.APP_NAME}-${className.trim()}.ics`;
};
