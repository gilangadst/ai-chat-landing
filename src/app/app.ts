import { Component } from '@angular/core';
import { LandingComponent } from './components/landing/landing';
import { ChatWidgetComponent } from './components/chat-widget/chat-widget';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [LandingComponent, ChatWidgetComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
