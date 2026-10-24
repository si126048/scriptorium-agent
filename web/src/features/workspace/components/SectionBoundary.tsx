import {Component,type ReactNode} from 'react';
import {Icon} from './Icon';
export class SectionBoundary extends Component<{children:ReactNode;name:string;resetKey?:string},{error:boolean}>{state={error:false};static getDerivedStateFromError(){return {error:true};}render(){return this.state.error?<div className="wb-section-error"><Icon name="refresh" size={24}/><h3>{this.props.name}暂时无法显示</h3><p>其他工作区域仍可使用，已保存的内容不会丢失。</p><button onClick={()=>this.setState({error:false})}>重新打开</button><button onClick={()=>window.location.reload()}>刷新应用</button></div>:this.props.children;}}
