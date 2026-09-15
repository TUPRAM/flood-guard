/** Integration test starting point. Adapt selectors to the actual semantic implementation.
 * Requires the implemented page and the repository Playwright config/baseURL.
 * Do not mark the site tested merely because this template is present.
 */
import {test,expect} from '@playwright/test';

test('hero is live HTML with direct workspace access',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{level:1,name:/See the flood.*Understand what it changes/s})).toBeVisible();
 await expect(page.getByRole('link',{name:'Explore the planning demo',exact:true}).first()).toHaveAttribute('href','/command/');
 await expect(page.locator('img[src*="/references/"],img[src*="/desktop/FG_"],img[src*="/mobile/FG_"]')).toHaveCount(0);
});

test('chapter navigation keeps the physical scene consistent',async({page})=>{
 await page.goto('/');
 const chapters=page.getByRole('navigation',{name:'Story chapters'});
 await chapters.getByRole('link',{name:/Connections affected/}).click();
 await expect(page.locator('[data-fg-active-scene="S3A-01"]')).toBeVisible();
 await chapters.getByRole('link',{name:/Everyday connections/}).click();
 await expect(page.locator('[data-fg-active-scene="S1-01"]')).toBeVisible();
});

test('the example observation is local and stays unverified',async({page})=>{
 const writes:string[]=[];page.on('request',r=>{if(['POST','PUT','PATCH','DELETE'].includes(r.method()))writes.push(r.url());});
 await page.goto('/#story-connections');
 const inspect=page.getByRole('button',{name:'Inspect sample observation',exact:true});
 await inspect.scrollIntoViewIfNeeded();await inspect.click();
 await expect(page.getByText(/Not verified\.?/, {exact:true}).first()).toBeVisible();
 expect(writes).toEqual([]);
});

test('reduced motion leaves the story and actions readable',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');
 await expect(page.getByRole('heading',{level:1})).toBeVisible();
 await page.getByRole('link',{name:'Explore the planning demo',exact:true}).first().focus();
 await expect(page.getByRole('link',{name:'Explore the planning demo',exact:true}).first()).toBeFocused();
});

test('no-JS fallback is a readable page, not a screenshot-only surface',async({browser,baseURL})=>{
 const context=await browser.newContext({javaScriptEnabled:false,baseURL});const page=await context.newPage();
 await page.goto('/');await expect(page.getByRole('heading',{level:1})).toBeVisible();
 await expect(page.getByRole('link',{name:'Explore the planning demo',exact:true}).first()).toHaveAttribute('href','/command/');
 await context.close();
});
