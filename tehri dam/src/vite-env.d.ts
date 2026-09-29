/// <reference types="vite/client" />

declare module 'lil-gui' {
  export default class GUI {
    constructor(opts?: { title?: string; width?: number; container?: HTMLElement; autoPlace?: boolean });
    domElement: HTMLElement;
    add(obj: any, prop: string, ...args: any[]): any;
    addFolder(name: string): GUI;
    close(): GUI;
    open(): GUI;
    controllersRecursive(): any[];
    destroy(): void;
  }
}
