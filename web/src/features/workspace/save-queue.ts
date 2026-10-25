/** All callers await the same in-flight flush. Rejection releases the queue for explicit retry. */
export class SaveQueue {
 private pending:Promise<void>|undefined;
 run(write:()=>Promise<void>):Promise<void>{
  if(this.pending)return this.pending;
  this.pending=Promise.resolve().then(write).finally(()=>{this.pending=undefined;});
  return this.pending;
 }
}
