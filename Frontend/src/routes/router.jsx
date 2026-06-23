import { createBrowserRouter } from 'react-router-dom';
import { AppLayout } from '@/layouts/AppLayout';
import { WelcomePage } from '@/pages/WelcomePage';
import { BuildAltarPage } from '@/pages/BuildAltarPage';
import { ChooseDesignPage } from '@/pages/ChooseDesignPage';
import { WorkspacePage } from '@/pages/WorkspacePage';
import { ResultPage } from '@/pages/ResultPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <WelcomePage /> },
      { path: 'build', element: <BuildAltarPage /> },
      { path: 'design', element: <ChooseDesignPage /> },
      { path: 'workspace', element: <WorkspacePage /> },
      { path: 'result', element: <ResultPage /> },
    ],
  },
]);
