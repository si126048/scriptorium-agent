export function HaloLayer({visible}:{visible:boolean}){
  if(!visible)return null;
  return <div className="fd-halo-layer" aria-hidden="true">
    <iframe src="/haloflux/index.html" title="HALOFLUX 环境光背景" tabIndex={-1} loading="lazy"/>
    <span className="fd-halo-veil"/>
  </div>;
}
