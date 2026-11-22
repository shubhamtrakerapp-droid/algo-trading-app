import React, { useEffect } from 'react';

/**
 * Login is permanently disabled.
 * The terminal operates in direct-access Read-Only Observational mode.
 * Any access automatically redirects to the terminal interface.
 */
export const Login: React.FC = () => {
  useEffect(() => {
    if (window.location.pathname !== '/') {
      window.location.replace('/');
    }
  }, []);

  return null;
};
