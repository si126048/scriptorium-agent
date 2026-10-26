import {useEffect} from 'react';
import {LogoSVG} from './LogoSVG';
import {loadConfig} from './startupConfig';
import {useWorkspaceUI} from '../../features/workspace/state';
interface Props{onComplete:()=>void;brandingOnly?:boolean}
export function StartupAnimation({onComplete}:Props){
 const quiet=useWorkspaceUI(s=>s.quiet);
 const enter=()=>{const config=loadConfig();if(!quiet&&config.sound){try{const audio=new AudioContext();const tone=audio.createOscillator();const volume=audio.createGain();volume.gain.value=Math.min(config.soundVolume,.1);tone.frequency.value=440;tone.connect(volume);volume.connect(audio.destination);tone.start();tone.stop(audio.currentTime+.06);tone.onended=()=>{void audio.close();};}catch{/* Audio is optional. */}}if(!quiet&&config.voice&&'speechSynthesis' in window){const voice=new SpeechSynthesisUtterance('Scriptorium');voice.rate=config.voiceRate;voice.volume=config.soundVolume;window.speechSynthesis.speak(voice);}onComplete();};
 useEffect(()=>{const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const timer=setTimeout(onComplete,quiet||reduced?160:1500);const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onComplete();};window.addEventListener('keydown',key);
 return()=>{clearTimeout(timer);window.removeEventListener('keydown',key);};},[onComplete,quiet]);
 return <div className="scriptorium-brand-entry"><LogoSVG size={68}/><strong>Scriptorium</strong><p>让问题、材料与解释相遇。</p><button onClick={enter}>进入工作台 <span>Esc</span></button></div>;
}
