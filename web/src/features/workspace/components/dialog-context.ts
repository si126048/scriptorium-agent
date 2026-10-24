import {createContext,useContext} from 'react';

export interface Dialogs {
  ask:(title:string,initial?:string)=>Promise<string|null>;
  confirm:(title:string)=>Promise<boolean>;
}

export const DialogsContext=createContext<Dialogs>(null!);

export const useDialogs=()=>useContext(DialogsContext);
