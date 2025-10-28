import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { ControlPlane, CognitoAuth } from '@cdklabs/sbt-aws';
import { CognitoConfig } from './constructs/cognito-config';
import { Config } from './config';

/**
 * Properties for the ControlPlaneStack
 */
export interface ControlPlaneStackProps extends StackProps {
  /**
   * Email address for the system administrator
   */
  readonly systemAdminEmail: string;
  
  /**
   * Whether to enable cross-region references
   */
  readonly crossRegionReferences?: boolean;
  
  /**
   * Callback URL for the control plane
   */
  readonly controlPlaneCallbackURL?: string;
}

/**
 * Stack that creates the control plane resources for the SaaS application
 */
export class ControlPlaneStack extends Stack {
  /**
   * The ARN of the event bus
   */
  public readonly eventBusArn: string;
  
  /**
   * The URL of the control plane API Gateway
   */
  public readonly controlPlaneUrl: string;
  
  /**
   * The client ID for the Cognito user pool client
   */
  public readonly clientId: string;
  
  /**
   * The authorization server URL
   */
  public readonly authorizationServer: string;
  
  /**
   * The well-known endpoint URL for OpenID Connect
   */
  public readonly wellKnownEndpointUrl: string;
  
  constructor(scope: Construct, id: string, props: ControlPlaneStackProps) {
    super(scope, id, props);

    // Get callback URL from props or use empty string as default
    const controlPlaneCallbackURL = props.controlPlaneCallbackURL || '';
    
    // Create Cognito authentication using our custom construct or the SBT one
    // Option 1: Use our custom CognitoConfig construct
    /*
    const cognitoConfig = new CognitoConfig(this, 'CognitoConfig', {
      userPoolName: 'SaaSControlPlaneUserPool',
      callbackUrls: [controlPlaneCallbackURL],
      setAPIGWScopes: false, // only for testing purposes!
      systemAdminEmail: props.systemAdminEmail,
    });
    
    // Create control plane with custom Cognito config
    // Note: This would require modifying the ControlPlane construct to accept our custom Cognito config
    */
    
    // Option 2: Use the SBT CognitoAuth construct (current approach)
    const cognitoAuth = new CognitoAuth(this, 'CognitoAuth', {
      setAPIGWScopes: false, // only for testing purposes!
      controlPlaneCallbackURL: controlPlaneCallbackURL,
    });

    // Create the control plane
    const controlPlane = new ControlPlane(this, 'ControlPlane', {
      systemAdminEmail: props.systemAdminEmail,
      auth: cognitoAuth,
    });

    // Set class properties
    this.controlPlaneUrl = controlPlane.controlPlaneAPIGatewayUrl;
    this.eventBusArn = controlPlane.eventManager.busArn;
    this.clientId = cognitoAuth.userClientId;
    this.wellKnownEndpointUrl = cognitoAuth.wellKnownEndpointUrl;
    const tokenEndpoint = cognitoAuth.tokenEndpoint;
    this.authorizationServer = tokenEndpoint.substring(0, tokenEndpoint.indexOf('/oauth2/token'));
    
    // Add outputs for easy reference
    new CfnOutput(this, 'ControlPlaneUrlOutput', {
      value: this.controlPlaneUrl,
      description: 'The URL of the Control Plane API Gateway',
    });
    
    new CfnOutput(this, 'EventBusArnOutput', {
      value: this.eventBusArn,
      description: 'The ARN of the Event Bus',
    });
    
    new CfnOutput(this, 'CognitoClientIdOutput', {
      value: this.clientId,
      description: 'The Cognito User Pool Client ID',
    });
  }
}
