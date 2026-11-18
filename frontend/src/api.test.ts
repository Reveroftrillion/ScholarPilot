import {describe,it,expect} from 'vitest';
import {pageWithin} from './api';
describe('PDF page input',()=>{it('clamps invalid values and fractional page numbers',()=>{expect(pageWithin(0,200)).toBe(1);expect(pageWithin(NaN,200)).toBe(1);expect(pageWithin(900,200)).toBe(200);expect(pageWithin(12.8,200)).toBe(12);});});
