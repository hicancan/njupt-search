import { useSearchExperience } from '@/app/routing/useSearchExperience';
import { HomePage } from '@/pages/home/HomePage';
import { ResultsPage } from '@/pages/results/ResultsPage';
import { AppFooter } from '@/widgets/app-shell/AppFooter';
import { BlockingDataError } from '@/widgets/app-shell/BlockingDataError';
import { Header } from '@/widgets/app-shell/Header';
import { InlineErrorBanner } from '@/widgets/app-shell/InlineErrorBanner';
import { DataUpdateToast } from '@/widgets/update-notifier/ui/DataUpdateToast';

function App() {
    const experience = useSearchExperience();

    if (experience.blockingError) {
        return <BlockingDataError {...experience.blockingError} />;
    }

    return (
        <div className="min-h-screen flex flex-col bg-white dark:bg-[#202124] text-[#202124] dark:text-[#e8eaed] transition-colors duration-200 font-sans">
            {!experience.isHome ? <Header {...experience.header} /> : null}

            <InlineErrorBanner message={experience.displayedError} />

            {experience.isHome ? (
                <HomePage {...experience.home} />
            ) : (
                <ResultsPage {...experience.results} />
            )}

            <AppFooter />
            <DataUpdateToast {...experience.updateToast} />
        </div>
    );
}

export default App;
