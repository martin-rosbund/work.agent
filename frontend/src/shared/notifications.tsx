import { createContext, useContext } from "react";

export type Notice = (message: string, error?: boolean) => void;

export const NoticeContext = createContext<Notice>(() => {});

export const useNotice = () => useContext(NoticeContext);
