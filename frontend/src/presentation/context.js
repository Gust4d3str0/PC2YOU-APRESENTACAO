import { createContext } from 'react';

// openCode(id): opens the Code Explorer drawer on a real snippet. lastAi: last real analysis run in this session.
export const PresentationContext = createContext({
  openCode: () => {}, lastAi: null, setLastAi: () => {}, goTo: () => {},
});
